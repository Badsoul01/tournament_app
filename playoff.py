from match import Match
from group import Group
from config import PLAYOFF_RULES
import math

class Playoff:
    """
    Třída zodpovědná za správu a logiku playoff, včetně generování kol,
    nasazovní hráčů, vyhodnocení BYE pozic a rekurzivních dohrávek o umístění.
    """

    def __init__(
            self,
            qualified_players:list,
            match_format:str,
            stage_name:str,
            playoff_elimination_action
    ) -> None:
        self.stage_name: str = stage_name
        self.players: list = qualified_players
        self.match_format: str = match_format
        self.waiting_room: list = []
        self.round_one_players: list = []
        self.eliminated_players: dict[int, list]  = {}
        self.rounds: dict[int, list] = {}
        self.winner = None

        self.playoff_elimination_action: str = playoff_elimination_action
        self.placement_rounds: dict[str, dict] = {}

    # ==========================================
    # VEŘEJNÉ API (HLAVNÍ METODY)
    # ==========================================

    def generate_full_bracket_structure(self,groups: dict, seeding_engine,start_rank: int = 1, end_rank: int=0) -> None:
        """
        Vygeneruje strukturu celého pavouka:
        - 1. kolo zůstává jako slotové n-tice (čekájící na dohrání skupin a převod na Match).
        - 2. a další kolo se generují jako prázdné objekty Match s navázanými vazbami pro postup vítězů.
        """
        # KROK 1: vytvoříme první kolo pavouka podle metody build_first_round

        slot_structure = seeding_engine.build_first_round(
            groups=groups,
            start_rank=start_rank,
            end_rank=end_rank
        )
        self.rounds[1] = slot_structure

        #  KROK 2:Spočítáme celkový počet kol podle velikosti 1.kola
        total_matches_in_round = len(slot_structure)
        # Počet kol je logaritmus o základu 2 (např. 4 zápasy = 2 kola, 8zápasu = 3 kola)
        num_rounds = math.ceil(math.log2(total_matches_in_round * 2)) if total_matches_in_round >0 else 1

        if num_rounds <2:
            return

        # KROK 3: Pro 2. a další kola předpřipravíme prázdné objekty Match
        # (Pozn.: Propojení s 1. se dokončí dynamicky ve chvíli, kdy se sloty v 1.kole přemění na Match).
        # Zde si vytvoříme strunkturu prázdných kol

        # Pro zjištění počtu zápasů v 2.kole (a dál)
        current_match_count = total_matches_in_round

        for r in range(2, num_rounds + 1):
            current_match_count = current_match_count // 2
            # V každém dalším kole je poloviční počet zápasů
            self.rounds[r] = [("Čeká se..","Čeká se..") for _ in range(current_match_count)]

        print(f"DEBUG: počet kol v pavouku: {self.rounds}")
        # KROK 4: vytvoříme slotovou dohrávku
        if self.playoff_elimination_action == "consolation":
            self.generate_placement_bracket_structure()

    def generate_placement_bracket_structure(self)-> None:
        """
        Vygeneruje předpřipravenou slotovou strukturu pro dohrávkové pavouky
        pro všechna kola hlavního pavouka, abychom pokryli kompletní umístění.
        """
        # Projdmee všechna kola v hlavním pavouku (kromě posledního, kde se hraje finále)
        main_rounds = sorted([r for r in self.rounds.keys() if isinstance(r,int)])

        if len(main_rounds) < 1:
            return

        # Celkový počet v 1.kole
        total_slots_in_main = len(self.rounds[1]) *2 #Celkový počet hráčů v prvním kole

        # Postupně projdeme kola hlavního pavouka a vytvoříme pro ně odpovídající dohrávkové bloky
        for r_idx, round_num in enumerate(main_rounds[:-1]):
            round_matches = self.rounds[round_num]
            num_losers = len(round_matches) # Počet poražených v tomto kole

            if num_losers <1:
                continue

            # Spočítáme rozsahy umístění (ranks) pro toto patro dohrávek
            # Z 1. kola padá nejvíce hráčů (spodní polovina pavouka), z dalších kol užší výběr
            if r_idx == 0:
                start_rank = (total_slots_in_main // 2) + 1
                end_rank = total_slots_in_main
            else:
                # Pro vyšší kola hlavního pavouka se umísťují hráči blíže k vrcholu dohrávek
                end_rank = (total_slots_in_main // (2** r_idx))
                start_rank = end_rank - num_losers + 1

            bracket_name = f"{start_rank}-{end_rank}"

            # Počet zápasů v tomto dohrávkovém patře je polovina počtu poražených
            placement_match_count = max(1, num_losers // 2)

            placement_slots = [("Čeká se..","Čeká se..") for _ in range(placement_match_count)]

            # Uložíme do struktury
            self.placement_rounds[bracket_name] = {
                "ranks": (start_rank,end_rank),
                "matches": placement_slots,
                "processed": False,
                "source_main_round": round_num # Poznamenáme si, ze kterého kola hlavního pavouka sem padají poražení
            }

            # Pokud má tento dohrávkový blok 2 nebo více zápasů (např. 4 a více hráčů)
            # rovnou dopředu předpřipravíme i pod.pavouky (pro vítěze a poražené)
            if placement_match_count >=2:
                self._pregenerate_sub_brackets_recursive(low=start_rank,high=end_rank,match_count=placement_match_count,source_main_round=round_num)


            print(f"DEBUG: Vygenerována slotová struktura dohrávky {bracket_name} pro poražené z hlavního kola #{round_num}.")

    def move_loser_to_placement_bracket(self, finished_match, round_num: int, match_index: int, tournament) -> None:
        """Posune PORAŽENÉHO  z hlavního pavouka do příslušného dohrávkového pavouka"""
        # 1. Zkontrolujeme, zda vůbec máme nějaké dohrávky aktivní/předpřipravené
        if not self.placement_rounds or finished_match.loser is None:
            return

        #Najdeme správný dohrávkový bracket, který odpovídá aktuálnímu kolu hlavního pavouka
        for bracket_name, bracket_data in self.placement_rounds.items():
            if bracket_data.get("source_main_round") == round_num:
                # Výpočítáme index zápasu a pozici (A/B) v dohrávce stejně jako v hlavním pavouku
                target_match_index = match_index // 2
                target_slot_position = "A" if match_index % 2 == 0 else "B"

                self._assign_player_to_slot(player=finished_match.loser, match_list=bracket_data["matches"],
                                            match_index=target_match_index, slot_position=target_slot_position,
                                            tournament=tournament)
                break

    def move_winner_to_next_round(self,finished_match, round_num: int,match_index: int, tournament) -> None:
        """Posouvá vítěze dohraného zápasu do slotu v následujícím kole."""
        next_round_num = round_num + 1
        if next_round_num not in self.rounds or finished_match.winner is None:
            return

        # Vypočítáme, do kterého zápasu (indexu) v dalším kole vítěz patří
        target_match_index = match_index // 2
        target_slot_position = "A" if match_index % 2 == 0 else "B"

        self._assign_player_to_slot(player=finished_match.winner, match_list=self.rounds[next_round_num],
                                    match_index=target_match_index, slot_position=target_slot_position,
                                    tournament=tournament)

    def move_placement_match_result(self,finished_match, bracket_name: str, match_index: int, tournament) -> None:
        """
        Okamžitě posune vítěze i poraženého z  dohrávkového zápasu do odpovídajícího slotu v navazujícím pod pavouku.)
        """
        if finished_match.winner is None:
            return

        low,high = self.placement_rounds[bracket_name]["ranks"]
        if low >= high:
            return

        mid = (low + high) // 2
        target_match_index = match_index // 2
        target_slot_position = "A" if match_index % 2 == 0 else "B"

        # Posun vítěze
        upper_name = f"{low}-{mid}"
        if upper_name in self.placement_rounds:
            self._assign_player_to_slot(
                player=finished_match.winner,
                match_list=self.placement_rounds[upper_name]["matches"],
                match_index=target_match_index,
                slot_position =target_slot_position,
                tournament=tournament
            )

        # Posun poraženého
        lower_name = f"{mid + 1}-{high}"
        if lower_name in self.placement_rounds and finished_match.loser is not None:
            self._assign_player_to_slot(
                player= finished_match.loser,
                match_list=self.placement_rounds[lower_name]["matches"],
                match_index= target_match_index,
                slot_position = target_slot_position,
                tournament=tournament
            )

    def update_slots_with_players(self,group_name: str, advancing_players: list, tournament, start_rank: int = 0) ->None:
        """Nahradí textové sloty (např. "1A") reálnými objekty hráčů po dohrání skupiny."""
        # 1.připravíme si mapování slotů na hráče pro tuto skupiny (např. "1A":Hráč1, "2A":Hráč2)
        slot_mapping = {}
        for index, player in enumerate(advancing_players, start=start_rank):
            rank = index + 1
            slot_name = f"{rank}{group_name}"
            slot_mapping[slot_name] = player

            # Můžeme hráči rovnou zapsat jeho umístění
            player.group_rank = str(rank)
            player.group_name = group_name

        # 2. Projdme první kolo playoff a pokusíme se nahradit sloty
        updated_round = []
        for i, item in enumerate(self.rounds[1]):
            if isinstance(item,tuple):
                slot_a, slot_b = item
                # Zkusíme nahradit slot_a (pokud je to string a patří do právě dohrané skupiny)
                if isinstance(slot_a, str) and slot_a in slot_mapping:
                    slot_a=slot_mapping[slot_a]
                # Zkusíme nahradit slot_b
                if isinstance(slot_b, str) and slot_b in slot_mapping:
                    slot_b= slot_mapping[slot_b]

                # 3. Zjistíme, zda jsou oba sloty vyřešené (nejsou to už stringy)
                resolved = self._resolve_slot_pair_to_match(slot_a=slot_a,slot_b=slot_b,tournament=tournament)
                updated_round.append(resolved)
            else:
                # Už je to hotový Match (vyřešený dříve), necháme ho být
                updated_round.append(item)

        # uložíme aktualizované kolo zpět
        self.rounds[1] = updated_round
        self.check_and_proceed(tournament=tournament)

    def check_and_proceed(self,tournament) -> bool:
        """
        Zkontroluje stav aktuálního kola hlavního poavouka i všech dohrávek
        a v případě dohrání automaticky vygeneruje kolo následující.
        """
        main_advance = False
        main_rounds = sorted([r for r in self.rounds.keys() if isinstance(r, int)])

        # Projdeme zápasy aktuálního kola hlavního pavouka
        for round_num in main_rounds:
            for idx,match in enumerate(self.rounds[round_num]):
                if isinstance(match, Match) and match.is_finished and  match.winner is not None:
                    # A) Standartní posun vítěze do dalšího kola hlavního pavouka
                    self.move_winner_to_next_round(
                        finished_match=match,
                        round_num=round_num,
                        match_index=idx,
                        tournament=tournament
                    )
                    print(f"DEBUG: Akce v playoff je: '{self.playoff_elimination_action}'")

                    # B) Pokud hrajeme dohrávky, pošleme poraženého do dohrávkového slotu!
                    if self.playoff_elimination_action == "consolation":
                        self.move_loser_to_placement_bracket(
                            finished_match=match,
                            round_num=round_num,
                            match_index=idx,
                            tournament=tournament
                    )
        # 2. Kontrola, zda skončilo finále (poslední kolo má už jen jeden zápas)
        for round_num, matches in self.rounds.items():
            if isinstance(round_num, int) and len(matches) ==1:
                if isinstance(matches[0], Match) and matches[0].is_finished and matches[0].winner is not None:
                    self.winner = matches[0].winner
                    print(f"DEBUG: Turnaj má celkového vítěze: {self.winner}")

        # 3. Kontrola stavu zápasů v dohrávkách (placement rounds)

        for bracket_name,data  in self.placement_rounds.items():
            for idx, match in enumerate(data["matches"]):
                if isinstance(match, Match) and match.is_finished and match.winner is not None:
                    if not getattr(match, "placement_result_moved", False):
                        self.move_placement_match_result(
                            finished_match=match,
                            bracket_name=bracket_name,
                            match_index=idx,
                            tournament=tournament
                        )
                        match.placement_result_moved = True

        return main_advance

    def get_sorted_placement_rounds(self):
        return sorted(self.placement_rounds.items(), key=lambda x: (x[1]["ranks"][1]-x[1]["ranks"][0], x[1]["ranks"][0]),
                      reverse=True)

    def _pregenerate_sub_brackets_recursive(self,low: int, high: int,match_count: int,source_main_round: int) -> None:
        """
        Rekursivně předpřipraví všechny pod-pavouky dohlubokých pater dohrávek
        (např. z 9-16 -> 9-12 a 13-16, z toho dál na 9-10, 11-12 atd).
        """
        if match_count <2:
            return

        mid= (low + high) // 2
        sub_match_count = max(1,match_count // 2)

        # 1.vštvovité pod-sloty pro vítěze (horní polovina)
        w_low, w_high = low, mid
        w_name = f"{w_low}-{w_high}"
        if w_name not in self.placement_rounds:
            self.placement_rounds[w_name] = {
                "ranks": (w_low, w_high),
                "matches": [("Čeká se..","Čeká se..") for _ in range(sub_match_count)],
                "processed": False,
                "source_main_round": source_main_round
            }
            # Rekursivní sestup pro ještě hlubší patra (pokud je co štěpit)
            self._pregenerate_sub_brackets_recursive(low=w_low,high=w_high,match_count=sub_match_count, source_main_round= source_main_round)

        # 2. Větvovité= pod-sloty pro poražené (dolní polovina)
        l_low, l_high = mid + 1, high
        l_name = f"{l_low}-{l_high}"

        if l_name not in self.placement_rounds:
            self.placement_rounds[l_name] = {
                "ranks": (l_low,l_high),
                "matches":[("Čeká se..","Čeká se..") for _ in range(sub_match_count)],
                "processed": False,
                "source_main_round": source_main_round
            }
            # Rekursivní sestup pro dolní větev
            self._pregenerate_sub_brackets_recursive(low=l_low,high=l_high,match_count=sub_match_count,source_main_round= source_main_round)

    def _resolve_slot_pair_to_match(self, slot_a, slot_b, tournament):
        """
        Pomocná metoda: zkrontroluje, zda jsou oba sloty v n-tici plné (vyřešené),
        a pokud ano, vytvoří a vrátí realný Match objekt. Jinak vrací zpět tuple.
        """

        # Slot je vytvořený, pokud to není string( což je "1A" nebo čeká se..")
        is_a_resolved = not isinstance(slot_a, str)
        is_b_resolved = not isinstance(slot_b, str)

        if is_a_resolved and is_b_resolved:
            # Oba hráči pro další kola jsou známí -> vytvoříme reálný Match!
            match = Match(
                player_a=slot_a,
                player_b=slot_b,
                match_format=self.match_format,
                tournament_stage=self.stage_name,
                match_id=tournament.get_next_match_id()
            )
            # Automotické vyhodnocení BYE zápasů.
            if slot_b is None and slot_a is not None:
                match.winner = slot_a
                match.is_finished = True
            elif slot_a is None and slot_b is not None:
                match.winner = slot_b
                match.is_finished = True
            elif slot_a is None and slot_b is None:
                match.is_finished = True

            return match

        else:
            return (slot_a, slot_b)

    def _assign_player_to_slot(self,player, match_list: list, match_index:int, slot_position: str, tournament) -> None:
        """
        Univerzální zapisovač: Vezme hráče a bezpečně ho zapíše do správného slotu.
        Pokud se tím slot zaplní oběma hráči, automaticky ho přemění na Match objekt.
        Tuto metodu využívají všechny funkce posouvající vítěze a poražené.
        """
        if match_index >=len(match_list):
            return

        target_item = match_list[match_index]

        # 1. varianta: V sezanmu je ještě prázdný tuple -> dosadíme hráče a zkusíme vytvořit Match
        if isinstance(target_item, tuple):
            slot_a, slot_b = target_item
            if slot_position == "A":
                slot_a = player
            else:
                slot_b = player

            # Pokus o vytvoření zápasu (pokud jsou oba hotoví)
            match_list[match_index] = self._resolve_slot_pair_to_match(slot_a=slot_a,slot_b=slot_b,tournament=tournament)

        elif isinstance(target_item, Match):
            if slot_position == "A":
                target_item.player_A = player
            else:
                target_item.player_B = player
