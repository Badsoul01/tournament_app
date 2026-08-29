import tournament
from models import db, Match as MatchModel, Player as PlayerModel, Bracket as BracketModel, Tournament as TournamentModel
from player import PlayerHelper
import math

class Playoff:
    """
    Třída zodpovědná za správu a logiku playoff, včetně generování kol,
    nasazování hráčů, vyhodnocení BYE pozic a dohrávek o umístění.
    Slouží jako "Slotový manažer", který vytváří databázové zápasy.
    """

    def __init__(
            self,
            tournament_id: int,
            match_format: int,
            stage_name: str,
            playoff_elimination_action: str,
            rank_offset: int = 0,
            bracket_id: int = None
    ) -> None:

        # Základní nastavení
        self.tournament_id: int = tournament_id
        self.stage_name: str = stage_name
        self.match_format: int = match_format
        self.playoff_elimination_action: str = playoff_elimination_action
        self.rank_offset = rank_offset
        self.bracket_id = bracket_id

        # Slovníky pro držení in-memory struktury (slotů a ID zápasů)
        self.rounds: dict[int, list] = {}
        self.placement_rounds: dict[str, dict] = {}

        self.winner = None

        if self.bracket_id:
            self.load_from_db()

    # ==========================================
    # VEŘEJNÉ API (HLAVNÍ METODY)
    # ==========================================

    def load_from_db(self):
        """Načte stav pavouka z JSON sloupce do paměti Pythonu."""
        bracket = BracketModel.query.get(self.bracket_id)
        if bracket and bracket.tree_data:
            # JSON automaticky mění číselné klíče na texty
            # Při načtení je zde překlopíme na zpět na čísla, aby fungovala matematika
            self.rounds = {int(k): v for k, v in bracket.tree_data.get("rounds",{}).items()}

            self.placement_rounds = bracket.tree_data.get("placement_rounds", {})

    def save_to_db(self):
        """Uloží aktuální úpravy zpět do JSON sloupce v databázi."""
        if not self.bracket_id:
            return

        bracket = BracketModel.query.get(self.bracket_id)
        if bracket:
            # překlopíme celou hodnotu, aby SQLAlchemy poznalo, že se JSON změnil
            bracket.tree_data = {
                "rounds": self.rounds,
                "placement_rounds": self.placement_rounds
            }
            db.session.commit()

    def generate_full_bracket_structure(self, groups: dict, seeding_engine, start_rank: int = 1, end_rank: int = 0) -> None:
        """
        Vygeneruje strukturu celého pavouka:
        - 1. kolo: Sloty pro nasazení ze skupin (např. "1A", "2B").
        - 2. a další kolo: Prázdné sloty ("Čeká se..", "Čeká se.."), které čekají na postupující.
        """
        # KROK 1: Vytvoříme první kolo pavouka pomocí seeding enginu
        slot_structure = seeding_engine.build_first_round(
            groups=groups,
            start_rank=start_rank,
            end_rank=end_rank
        )
        self.rounds[1] = slot_structure

        # KROK 2: Spočítáme celkový počet kol pavouka (např. 8 zápasů = 4 kola)
        total_matches_in_round = len(slot_structure)
        num_rounds = math.ceil(math.log2(total_matches_in_round * 2)) if total_matches_in_round > 0 else 1

        if num_rounds < 2:
            return

        # KROK 3: Pro 2. a další kola předpřipravíme prázdné slotové n-tice
        current_match_count = total_matches_in_round

        for r in range(2, num_rounds + 1):
            current_match_count = current_match_count // 2
            self.rounds[r] = [("Čeká se..", "Čeká se..") for _ in range(current_match_count)]

        print(f"DEBUG: Počet kol v pavouku: {len(self.rounds)}")

        # KROK 4: Příprava struktury pro dohrávky o umístění
        if self.playoff_elimination_action == "consolation":
            self.generate_placement_bracket_structure()

    def generate_placement_bracket_structure(self) -> None:
        """
        Vygeneruje předpřipravenou slotovou strukturu pro dohrávkové pavouky
        pro všechna kola hlavního pavouka, abychom pokryli kompletní umístění.
        """
        main_rounds = sorted([r for r in self.rounds.keys() if isinstance(r, int)])

        if len(main_rounds) < 1:
            return

        total_slots_in_main = len(self.rounds[1]) * 2

        for r_idx, round_num in enumerate(main_rounds[:-1]):
            round_matches = self.rounds[round_num]
            num_losers = len(round_matches)

            if num_losers < 1:
                continue

            if r_idx == 0:
                start_rank = (total_slots_in_main // 2) + 1
                end_rank = total_slots_in_main
            else:
                end_rank = (total_slots_in_main // (2 ** r_idx))
                start_rank = end_rank - num_losers + 1

            start_rank += self.rank_offset
            end_rank += self.rank_offset

            bracket_name = f"{start_rank}-{end_rank}"
            placement_match_count = max(1, num_losers // 2)

            self.placement_rounds[bracket_name] = {
                "ranks": (start_rank, end_rank),
                "matches": [("Čeká se..", "Čeká se..") for _ in range(placement_match_count)],
                "processed": False,
                "source_main_round": round_num
            }

            if placement_match_count >= 2:
                self._pregenerate_sub_brackets_recursive(
                    low=start_rank,
                    high=end_rank,
                    match_count=placement_match_count,
                    source_main_round=round_num
                )
        print("DEBUG: Vygenerována slotová struktura dohrávek o umístění.")

    def move_loser_to_placement_bracket(self, db_match, round_num: int, match_index: int) -> None:
        """Posune PORAŽENÉHO z hlavního pavouka do příslušného dohrávkového pavouka."""
        if not self.placement_rounds or db_match.winner_id is None:
            return

        # Určíme ID poraženého (ten, kdo není vítěz)
        loser_id = db_match.player_b_id if db_match.winner_id == db_match.player_a_id else db_match.player_a_id

        for bracket_name, bracket_data in self.placement_rounds.items():
            if bracket_data.get("source_main_round") == round_num:
                target_match_index = match_index // 2
                target_slot_position = "A" if match_index % 2 == 0 else "B"

                self._assign_player_to_slot(
                    player_id=loser_id,
                    match_list=bracket_data["matches"],
                    match_index=target_match_index,
                    slot_position=target_slot_position
                )
                break

    def move_winner_to_next_round(self, db_match, round_num: int, match_index: int) -> None:
        """Posouvá VÍTĚZE dohraného zápasu do slotu v následujícím kole."""
        next_round_num = round_num + 1
        if next_round_num not in self.rounds or db_match.winner_id is None:
            return

        target_match_index = match_index // 2
        target_slot_position = "A" if match_index % 2 == 0 else "B"

        self._assign_player_to_slot(
            player_id=db_match.winner_id,
            match_list=self.rounds[next_round_num],
            match_index=target_match_index,
            slot_position=target_slot_position
        )

    def move_placement_match_result(self, db_match, bracket_name: str, match_index: int) -> None:
        """Posune vítěze i poraženého z dohrávkového zápasu hlouběji do pod-pavouka."""
        if db_match.winner_id is None:
            return

        loser_id = db_match.player_b_id if db_match.winner_id == db_match.player_a_id else db_match.player_a_id
        low, high = self.placement_rounds[bracket_name]["ranks"]
        if low >= high:
            return

        mid = (low + high) // 2
        target_match_index = match_index // 2
        target_slot_position = "A" if match_index % 2 == 0 else "B"

        # Posun vítěze nahoru
        upper_name = f"{low}-{mid}"
        if upper_name in self.placement_rounds:
            self._assign_player_to_slot(
                player_id=db_match.winner_id,
                match_list=self.placement_rounds[upper_name]["matches"],
                match_index=target_match_index,
                slot_position=target_slot_position
            )

        # Posun poraženého dolů
        lower_name = f"{mid + 1}-{high}"
        if lower_name in self.placement_rounds:
            self._assign_player_to_slot(
                player_id=loser_id,
                match_list=self.placement_rounds[lower_name]["matches"],
                match_index=target_match_index,
                slot_position=target_slot_position
            )

    def update_slots_with_players(self, group_name: str, advancing_players: list, start_rank: int = 0) -> None:
        """
        Nahradí textové sloty (např. "1A") reálnými ID HRÁČŮ po dohrání skupiny.
        """
        # Vytvoříme mapování: "1A" -> 5 (kde 5 je ID hráče v DB)
        slot_mapping = {}
        for index, player in enumerate(advancing_players, start=start_rank):
            rank = index + 1
            slot_name = f"{rank}{group_name}"
            slot_mapping[slot_name] = player.id  # Ukládáme jen jeho DB ID

        updated_round = []
        for item in self.rounds[1]:
            if isinstance(item, (tuple,list)):
                slot_a, slot_b = item

                # Zkusíme nahradit "1A" za reálné ID
                if isinstance(slot_a, str) and slot_a in slot_mapping:
                    slot_a = slot_mapping[slot_a]
                if isinstance(slot_b, str) and slot_b in slot_mapping:
                    slot_b = slot_mapping[slot_b]

                # Zkusíme vyřešit a vytvořit Match
                resolved = self._resolve_slot_pair_to_match(slot_a, slot_b)
                updated_round.append(resolved)
            else:
                updated_round.append(item)

        self.rounds[1] = updated_round

        # PŘIDÁNO: Automaticky zkontrolujeme vytvořené zápasy a posuneme vítěze BYE dál!
        self.check_and_proceed()

    def check_and_proceed(self) -> None:
        """
        Hlavní motor pavouka. Zkontroluje aktuální stav všech vygenerovaných
        zápasů v DB. Pokud najde dohraný zápas, automaticky posune hráče dál
        a zapíše konečná umístění pro dohrané finálové zápasy.
        """

        main_rounds = sorted([r for r in self.rounds.keys() if isinstance(r, int)])

        # 1. HLAVNÍ PAVOUK - kontrola a posun
        for round_num in main_rounds:
            for idx, item in enumerate(self.rounds[round_num]):
                # Pokud je slot integer, znamená to, že obsahuje ID databázového zápasu
                if isinstance(item, int):
                    db_match = MatchModel.query.get(item)

                    if db_match and db_match.is_finished and db_match.winner_id is not None:
                        # Zápas je hotový -> posouváme hráče dál
                        self.move_winner_to_next_round(db_match, round_num, idx)

                        if self.playoff_elimination_action == "consolation":
                            self.move_loser_to_placement_bracket(db_match, round_num, idx)

        # 2. URČENÍ CELKOVÉHO VÍTĚZE A ZÁPIS FINÁLE
        if main_rounds:
            last_round = main_rounds[-1]
            if len(self.rounds[last_round]) == 1:
                item = self.rounds[last_round][0]
                if isinstance(item, int):
                    db_match = MatchModel.query.get(item)
                    if db_match and db_match.is_finished and db_match.winner_id is not None:
                        self.winner = db_match.winner_id
                        print(f"DEBUG: Turnaj má celkového vítěze (ID hráče): {self.winner}")
                        # Vítěz finále bere první pozici s offsetem
                        PlayerHelper.set_final_rank(self.winner, 1 + self.rank_offset, stage_name=self.stage_name)

                        # Poražený ve finále bere hned následující pozici (offset + 2)
                        loser_id = db_match.player_b_id if db_match.winner_id == db_match.player_a_id else db_match.player_a_id
                        if loser_id:
                            PlayerHelper.set_final_rank(loser_id, 2 + self.rank_offset,stage_name=self.stage_name)

        # 3. DOHRÁVKY - kontrola, posun a ZÁPIS KONEČNÝCH UMÍSTĚNÍ
        for bracket_name, data in self.placement_rounds.items():
            low, high = data["ranks"]

            for idx, item in enumerate(data["matches"]):
                if isinstance(item, int):
                    db_match = MatchModel.query.get(item)
                    if db_match and db_match.is_finished and db_match.winner_id is not None:
                        # 1. Posuneme hráče v pavouku dál (např. z 5-8 do 5-6 nebo 7-8)
                        self.move_placement_match_result(db_match, bracket_name, idx)

                        # 2. Pokud se hraje PŘÍMO o konkrétní dvě místa (rozdíl je 1, např. 3-4, 5-6), zapíšeme to do DB!
                        if high - low == 1:
                            loser_id = db_match.player_b_id if db_match.winner_id == db_match.player_a_id else db_match.player_a_id

                            # Vítěz bere nižší číslo (např. 3), poražený vyšší (např. 4)
                            PlayerHelper.set_final_rank(db_match.winner_id, low, stage_name=self.stage_name)
                            if loser_id:
                                PlayerHelper.set_final_rank(loser_id, high, stage_name=self.stage_name)

    def get_sorted_placement_rounds(self):
        return sorted(self.placement_rounds.items(), key=lambda x: (x[1]["ranks"][1]-x[1]["ranks"][0], x[1]["ranks"][0]),
                      reverse=True)


    def _pregenerate_sub_brackets_recursive(self,low: int, high: int,match_count: int,source_main_round: int) -> None:
        """Rekurzivně předpřipraví pod-pavouky hlubších pater dohrávek."""
        if match_count < 2:
            return

        mid = (low + high) // 2
        sub_match_count = max(1, match_count // 2)

        # Horní polovina (vítězové dohrávky)
        w_name = f"{low}-{mid}"
        if w_name not in self.placement_rounds:
            self.placement_rounds[w_name] = {
                "ranks": (low, mid),
                "matches": [("Čeká se..", "Čeká se..") for _ in range(sub_match_count)],
                "processed": False,
                "source_main_round": source_main_round
            }
            self._pregenerate_sub_brackets_recursive(low, mid, sub_match_count, source_main_round)

        # Dolní polovina (poražení dohrávky)
        l_name = f"{mid + 1}-{high}"
        if l_name not in self.placement_rounds:
            self.placement_rounds[l_name] = {
                "ranks": (mid + 1, high),
                "matches": [("Čeká se..", "Čeká se..") for _ in range(sub_match_count)],
                "processed": False,
                "source_main_round": source_main_round
            }
            self._pregenerate_sub_brackets_recursive(mid + 1, high, sub_match_count, source_main_round)

    def _resolve_slot_pair_to_match(self, slot_a, slot_b):
        """
        Zkontroluje, zda jsou oba sloty plné (obsahují ID hráče nebo 'BYE' / None).
        Pokud ano, založí MatchModel v databázi a vrátí jeho ID.
        Jinak vrátí původní tuple (např. (15, 'Čeká se..')).
        """

        # OPRAVA 1: Zpracujeme "BYE", textové "None" i skutečný Python objekt None
        def is_resolved(slot):
            return isinstance(slot, int) or slot in ("BYE", None, "None")

        if is_resolved(slot_a) and is_resolved(slot_b):
            # Zjistíme reálná IDs (pokud je to BYE nebo None, ID bude None)
            p_a_id = slot_a if isinstance(slot_a, int) else None
            p_b_id = slot_b if isinstance(slot_b, int) else None

            # Vytvoříme databázový zápas
            db_match = MatchModel(
                match_type="playoff",
                match_format=str(self.match_format),
                tournament_id=self.tournament_id,
                bracket_id=self.bracket_id,
                player_a_id=p_a_id,
                player_b_id=p_b_id,
                is_finished=False
            )

            # OPRAVA 2: Vyhodnocení BYE rovnou na základě None IDček
            if p_b_id is None and p_a_id is not None:
                db_match.winner_id = p_a_id
                db_match.is_finished = True
            elif p_a_id is None and p_b_id is not None:
                db_match.winner_id = p_b_id
                db_match.is_finished = True
            elif p_a_id is None and p_b_id is None:
                # Velmi vzácné (dvě prázdná místa jdou proti sobě)
                db_match.is_finished = True
                db_match.winner_id = None

            db.session.add(db_match)
            db.session.commit()

            return db_match.id

        else:
            # Ještě chybí hráč, vracíme původní tuple
            return slot_a, slot_b

    def _assign_player_to_slot(self, player_id: int, match_list: list, match_index: int, slot_position: str) -> None:
        """
        Univerzální zapisovač pro posouvání hráčů (vítězů/poražených) do dalších kol.
        """
        if match_index >= len(match_list):
            return

        target_item = match_list[match_index]

        # A) V daném místě je ještě tuple (čeká se na spojení dvou hráčů)
        if isinstance(target_item, (tuple, list)):
            slot_a, slot_b = target_item
            if slot_position == "A":
                slot_a = player_id
            else:
                slot_b = player_id

            # Zkusíme rovnou vyřešit, zda už náhodou nejsou oba plné
            match_list[match_index] = self._resolve_slot_pair_to_match(slot_a, slot_b)

        # B) V daném místě už je číslo (ID zápasu) - což se stane, pokud se dříve vytvořil zápas
        elif isinstance(target_item, int):
            db_match = MatchModel.query.get(target_item)
            if db_match:
                if slot_position == "A":
                    db_match.player_a_id = player_id
                else:
                    db_match.player_b_id = player_id
                db.session.commit()

    def get_ui_data(self) -> dict:
        """Vygeneruje data o pavouku ve formátu vhodném pro HTML šablonu."""
        p_data = {"rounds": {}, "placement_rounds": [], "winner": None}
        tournament = TournamentModel.query.get(self.tournament_id)


        # Zpracování hlavních kol
        for round_num, matches in self.rounds.items():
            round_ui = []
            for item in matches:
                if isinstance(item, int):  # Je to vygenerovaný databázový zápas
                    m = MatchModel.query.get(item)
                    round_ui.append({
                        "is_real_match": True,
                        "match_id": m.id,
                        "player_a_name": m.player_a.name if m.player_a else "BYE",
                        "player_a_seed": m.player_a.group_seed if m.player_a else "",
                        "player_b_name": m.player_b.name if m.player_b else "BYE",
                        "player_b_seed": m.player_b.group_seed if m.player_b else "",
                        "is_finished": m.is_finished,
                        "is_in_progress": getattr(m, "is_in_progress", False),
                        "match_format": m.playoff_match_format,
                        "winner_name": m.winner.name if m.winner else None
                    })
                else:  # Prázdný slot ("1A", "2B") nebo "Čeká se.."
                    slot_a, slot_b = item
                    slot_a_seed, slot_b_seed = "", ""

                    if isinstance(slot_a, int):
                        p = PlayerModel.query.get(slot_a)
                        slot_a = p.name if p else "TBD"
                        slot_a_seed = p.group_seed if p else ""
                    elif slot_a is None or slot_a == "None":
                        slot_a = "BYE"
                    if isinstance(slot_b, int):
                        p = PlayerModel.query.get(slot_b)
                        slot_b = p.name if p else "TBD"
                        slot_b_seed = p.group_seed if p else ""
                    elif slot_b is None or slot_b == "None":
                        slot_b = "BYE"

                    round_ui.append({
                        "is_real_match": False,
                        "slot_a": slot_a,
                        "slot_a_seed": slot_a_seed,
                        "slot_b": slot_b,
                        "slot_b_seed": slot_b_seed
                    })
            p_data["rounds"][round_num] = round_ui

        # Zpracování dohrávek (placement rounds)
        for bracket_name, data in self.placement_rounds.items():
            placement_ui = {"name": bracket_name, "matches": []}
            for item in data["matches"]:
                if isinstance(item, int):
                    m = MatchModel.query.get(item)
                    placement_ui["matches"].append({
                        "is_real_match": True,
                        "match_id": m.id,
                        "player_a_name": m.player_a.name if m.player_a else "BYE",
                        "player_a_seed": m.player_a.group_seed if m.player_a else "",
                        "player_b_name": m.player_b.name if m.player_b else "BYE",
                        "player_b_seed": m.player_b.group_seed if m.player_b else "",
                        "is_finished": m.is_finished,
                        "is_in_progress": getattr(m, "is_in_progress", False),
                        "match_format": m.playoff_match_format,
                        "winner_name": m.winner.name if m.winner else None
                    })
                else:
                    slot_a, slot_b = item
                    if isinstance(slot_a, int):
                        p = PlayerModel.query.get(slot_a)
                        slot_a = p.name if p else "TBD"
                    elif slot_a is None or slot_a == "None":
                        slot_a = "BYE"

                    if isinstance(slot_b, int):
                        p = PlayerModel.query.get(slot_b)
                        slot_b = p.name if p else "TBD"
                    elif slot_b is None or slot_b == "None":
                        slot_b = "BYE"

                    placement_ui["matches"].append({
                        "is_real_match": False,
                        "slot_a": slot_a,
                        "slot_b": slot_b
                    })
            p_data["placement_rounds"].append(placement_ui)

        # Zjištění celkového vítěze pavouka
        if self.winner:
            w = PlayerModel.query.get(self.winner)
            p_data["winner"] = w.name if w else None

        return p_data
