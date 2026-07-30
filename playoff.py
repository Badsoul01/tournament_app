import seedingengine
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
        """
        Vezme poraženého z dohraného zápasu hlavního pavouka a posune ho do správného slotu
        v odpovídajícím dohrávkovém pavouku podle kola, ve kterém vypadl.
        """
        # 1. Zkontrolujeme, zda vůbec máme nějaké dohrávky aktivní/předpřipravené
        print(f"DEBUG: Hledám bracket pro source_main_round={round_num}. Dostupné v placement_rounds: {[d.get('source_main_round') for d in self.placement_rounds.values()]}")
        if not self.placement_rounds:
            return

        # 2. Určíme poraženého z právě dohraného zápasu hlavního kola
        # (pokud nějaký hráč chybí -např. BYE, poražený neexistuje)
        if finished_match.player_A is None or finished_match.player_B is None:
            return

        loser = finished_match.player_B if finished_match.winner == finished_match.player_A else finished_match.player_A
        if loser is None:
            return

        # 3. Najdeme správný dohrávkový bracket, který odpovídá aktuálnímu kolu hlavního pavouka
        for bracket_name, bracket_data in self.placement_rounds.items():
            if bracket_data.get("source_main_round") == round_num:
                placement_matches = bracket_data["matches"]

                # Výpočítáme index zápasu a pozici (A/B) v dohrávce stejně jako v hlavním pavouku
                target_match_index = match_index // 2
                target_slot_position = "A" if match_index % 2 == 0 else "B"

                if target_match_index < len(placement_matches):
                    target_item = placement_matches[target_match_index]

                    # Pokud je v dohrávce na daném indexu stále slot (tuple) dosadíme poraženého
                    if isinstance(target_item, tuple):
                        slot_a, slot_b = target_item
                        if target_slot_position == "A":
                            slot_a = loser
                        else:
                            slot_b = loser

                        # Využijeme existující metodu, která zkontroluje, oba poražené a případně vytvoří Match
                        resolved = self._resolve_slot_pair_to_match(slot_a=slot_a,slot_b=slot_b,tournament=tournament)
                        placement_matches[target_match_index] = resolved
                    elif isinstance(target_item,Match):
                        if target_slot_position == "A":
                            target_item.player_A = loser
                        else:
                            target_item.player_B = loser

    def move_winner_to_next_round(self,finished_match, round_num: int,match_index: int, tournament) -> None:
        """
        Posouvá vítěze dohraného zápasu do slotu v následujícím kole.
        Pokud jsou v příším kole obsazeny oba sloty, vytvoří z nich reálný Match.
        """
        next_round_num = round_num + 1
        if next_round_num not in self.rounds:
            return

        # Vypočítáme, do kterého zápasu (indexu) v dalším kole vítěz patří
        target_match_index = match_index // 2
        target_slot_position = "A" if match_index % 2 == 0 else "B"

        next_round_items = self.rounds[next_round_num]

        # Zkontrolujeme, zda na cílovém indexu exituje slot (tuple) nebo už reálný Match
        if target_match_index <len(next_round_items):
            target_item = next_round_items[target_match_index]
            winner = finished_match.winner
            # Pokud je v dalším kole stále slot(tuple), pracujeme s ním
            if isinstance(target_item, tuple):
                slot_a,slot_b = target_item

                if target_slot_position == "A":
                    slot_a = winner
                else:
                    slot_b = winner

                resolved = self._resolve_slot_pair_to_match(slot_a=slot_a,slot_b=slot_b,tournament=tournament)
                next_round_items[target_match_index] = resolved
            elif isinstance(target_item,Match):
                if target_slot_position == "A":
                    target_item.player_A = winner
                else:
                    target_item.player_B = winner



    def process_placement_bracket(self,bracket_name: str,tournament) -> None:
        """
        Hlavní řídící metoda pro dohrávky - vyhodnotí aktuální fázi
        a případně rekurzivě vytoří pod-pavouky pro vítěze a poražené.
        """
        #1.získání dat o bracketu
        bracket_data = self.placement_rounds[bracket_name]
        matches = bracket_data["matches"]

        #1. Získání výsledků
        results = self._get_bracket_results(matches)

        #2. Ukončení, pokud je bracket hotový
        if len(matches) == 1:
            self._finalize_ranking_positions(bracket_name,results)
            return

        #3. Rekurzivní tvorka dalších úrovní (pouze pokud máme hráče k párování)
        if len(results["winners"]) >= 1:
            self._create_sub_bracket(bracket_name,results["winners"], "winners",tournament)
        if len(results["losers"]) >= 1:
            self._create_sub_bracket(bracket_name,results["losers"], "losers",tournament)




    def update_slots_with_players(self,group_name: str, advancing_players: list, tournament) ->None:
        """
        Nahradí textové sloty (např. "1A") reálnými objekty hráčů po dohrání skupiny.
        Pokud jsou oba sloty v n-tici zaplněny, vytvoří reálný objekt Match.
        """
        # 1.připravíme si mapování slotů na hráče pro tuto skupiny (např. "1A":Hráč1, "2A":Hráč2)
        slot_mapping = {}
        for index, player in enumerate(advancing_players):
            rank = index + 1
            slot_name = f"{rank}{group_name}"
            slot_mapping[slot_name] = player

            # Můžeme hráči rovnou zapsat jeho umístění
            player.group_rank = str(rank)
            player.group_name = group_name

        # 2. Projdme první kolo playoff a pokusíme se nahradit sloty
        current_round = self.rounds[1]
        updated_round = []

        for i, item in enumerate(current_round):
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

    def check_and_proceed(self,tournament) -> bool:
        """
        Zkontroluje stav aktuálního kola hlavního poavouka i všech dohrávek
        a v případě dohrání automaticky vygeneruje kolo následující.
        """
        main_advance = False

        main_rounds = sorted([r for r in self.rounds.keys() if isinstance(r, int)])

        # Projdeme zápasy  aktuálního kola hlavního pavouka
        for round_num in main_rounds:
            matches = self.rounds[round_num]

            for idx,match in enumerate(matches):
                if isinstance(match, Match) and match.is_finished and  match.winner is not None:
                    # A) Standartní posun vítěze do dalšího kola hlavního pavouka
                    self.move_winner_to_next_round(
                        finished_match=match,
                        round_num=round_num,
                        match_index=idx,
                        tournament=tournament
                    )
                    print(f"DEBUG: Akce v playoff je: '{self.playoff_elimination_action}'")

                    # B) Pokud jsme v prvního kole a hrajeme dohrávky, pošleme poraženého do dohrávkového slotu!
                    if round_num == 1 and  self.playoff_elimination_action == "consolation":
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
        keys_to_process = [bracket_name for bracket_name in self.placement_rounds.keys()]
        for bracket_name in keys_to_process:
            data = self.placement_rounds[bracket_name]
            matches = data["matches"]

            # Filtrujeme jen reálné Match objekty (ignorujeme nevyplněné sloty)
            real_matches = [m for m in matches if isinstance(m, Match)]

            # Pokud už máme vytvořené zápasy a všechny jsou hotové
            if real_matches and all(m.is_finished for m in real_matches) and not data["processed"]:
                print(f"DEBUG: Všechny zápasy v dohrávce {bracket_name} jsou hotové, zpracovávám.. ")
                self.process_placement_bracket(bracket_name=bracket_name,tournament=tournament)
                data["processed"] = True

        return main_advance

    def get_seeded_players(self,players,advance_per_group: int) -> list:
        """
        Vrátí chytře seřazený seznam hráčů pro nasazení do playoff tak,
        aby se hráči ze stejných skupin nepotkali příliš brzy.
        """
        if not players:
            return players
        by_group = {}
        for p in players:
            by_group.setdefault(p.group_name,[]).append(p)
            by_group[p.group_name].sort(key=lambda x: x.group_rank or 99)

        group_keys = sorted(by_group.keys())
        high_ranks =[]
        for r in range(advance_per_group // 2):
            for g in group_keys:
                if r < len(by_group[g]):
                    high_ranks.append(by_group[g][r])

        low_ranks = []

        for r in range(advance_per_group // 2, advance_per_group):
            for g in group_keys:
                if r < len(by_group[g]):
                    low_ranks.append(by_group[g][r])

        return high_ranks + low_ranks

    def get_placement_losers_from_first_round(self,first_round_matches: list) -> list:
        """
        Prochází zápasy 1.kola seshora dolů a vrací seznam
        poražených respektující původní pozice v pavouku.(včetně None pro BYE větve).
        """
        placement_losers = []

        for match in first_round_matches:
            if match.player_A is None or match.player_B is None:
                placement_losers.append(None)
            elif match.is_finished and match.winner is not None:
                loser = match.player_B if match.winner == match.player_A else match.player_A
                placement_losers.append(loser)

        return placement_losers

    def get_sorted_placement_rounds(self):
        return sorted(self.placement_rounds.items(), key=lambda x: (x[1]["ranks"][1]-x[1]["ranks"][0], x[1]["ranks"][0]),
                      reverse=True)

    def generate_full_bracket_structure(self,groups: dict, advance_per_group: int, seeding_engine) -> None:
        """
        Vygeneruje strukturu celého pavouka:
        - 1. kolo zůstává jako slotové n-tice (čekájící na dohrání skupin a převod na Match).
        - 2. a další kolo se generují jako prázdné objekty Match s navázanými vazbami pro postup vítězů.
        """
        # KROK 1: vytvoříme první kolo pavouka podle metody build_first_round

        slot_structure = seeding_engine.build_first_round(
            groups=groups,
            advance_per_group=advance_per_group
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
            next_round_slots = []

            # V každém dalším kole je poloviční počet zápasů
            for i in range(current_match_count):
                # Vytvoříme slotovnou n-tici pro budoucí zápas
                next_round_slots.append(("Čeká se..", "Čeká se.."))

                self.rounds[r] = next_round_slots
        print(f"DEBUG: počet kol v pavouku: {self.rounds}")
        # KROK 4: vytvoříme slotovou dohrávku
        if self.playoff_elimination_action == "consolation":
            self.generate_placement_bracket_structure()


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

    def _resolve_slot_pair_to_match(self, slot_a, slot_b,tournament):
        """
        Pomocná metoda: zkrontroluje, zda jsou oba sloty v n-tici plné (vyřešené),
        a pokud ano, vytvoří a vrátí realný Match objekt. Jinak vrací zpět tuple.
        """

        # Slot je vytvořený, pokud to není string( což je "1A" nebo čeká se..") a zároveň to není None
        is_a_resolved = not isinstance(slot_a, str) and slot_a is not None
        is_b_resolved = not isinstance(slot_b, str) and slot_b is not None

        if is_a_resolved and is_b_resolved:
            # Oba hráči pro další kola jsou známí -> vytvoříme reálný Match!
            return  Match(
                player_a=slot_a,
                player_b=slot_b,
                match_format=self.match_format,
                tournament_stage=self.stage_name,
                match_id=tournament.get_next_match_id()
            )
        else:
            return (slot_a, slot_b)



    def _create_placement_bracket_matches(self,players_with_none: list,tournament) -> list:
        """
        Vytvoří zápasy pro dohrávku. Jednotně zpracovává sudý i lichý počet hráčů
        a respektuje pevné pozice (včetně None pro BYE).
        """
        matches = []
        n = len(players_with_none)

        for i in range(n // 2):
            player_A = players_with_none[i]
            player_B = players_with_none[n-1-i]

            # Pokud jsou oba sloty prázné, zápas nevytváříme
            if player_A is None and player_B is None:
                continue
            # Pokud je hráč A prázdný, prohodíme je, aby aktivní hráč byl vždy na  pozici A
            if player_A is None and player_B is not None:
                player_A, player_B = player_B, player_A

            match= Match(
                player_a=player_A,
                player_b=player_B,
                match_format=self.match_format,
                tournament_stage=self.stage_name,
                match_id=tournament.get_next_match_id()
            )

            # Pokud jde o BYE zápas (chybí soupeř), automaticky vyhrává přitomný hráč
            if player_B is None:
                match.winner = player_A
                match.is_finished = True

            matches.append(match)

        return matches

    def _get_bracket_results(self,matches: list) -> dict[str, list]:
        """
        Pomocná metoda pro sběr vítězů a poražených z předchozích zápasů.
        """
        winners = []
        losers = []

        for m in matches:
            if isinstance(m,Match) and m.is_finished and m.winner is not None:
                winners.append(m.winner)
                # Bezpečně dopočítáme poraženého
                if m.player_A is not None and m.player_B is not None:
                    loser = m.player_B if m.winner == m.player_A else m.player_A
                    losers.append(loser)
        return {
            "winners": winners,
            "losers": losers
        }

    def _create_sub_bracket(self,parent_name: str,players: list,side: str,tournament) -> None:
        """
        Vytvoří pod-pavouka na základě výsledků předchozího kola (pro "winners" nebo "losers").
        """
        # Získání původních rozsahů
        low,high = self.placement_rounds[parent_name]["ranks"]
        half_len = max(1,len(players)//2)

        if side == "winners":
            new_ranks = (low, low+len(players)-1 if len(players)<=2 else low+half_len-1)
            new_name = f"{new_ranks[0]}-{new_ranks[1]}"
        else:
            mid = (low + high) // 2 if low !=high else low
            start_rank= mid+1 if mid < high else high
            new_ranks = (start_rank,high)
            if new_ranks[0]> new_ranks[1]:
                new_ranks = (high,high)
            new_name = f"{new_ranks[0]}-{new_ranks[1]}"

        if new_name == parent_name:
            new_name = f"{low}-{high}"

        if new_name in self.placement_rounds:
            print(f"DEBUG: Pod-pavouk {new_name} již existuje,přeskakuji tvorbu")
            return

        # Pokud máme méně hráčů, připravíme pole pro vytvoření zápasu.
        bracket_players= list(players)
        if len(bracket_players) == 1:
            bracket_players.append(None)

        sub_matches = self._create_placement_bracket_matches(bracket_players,tournament=tournament)
        #Zjistíme source_main_round  z rodičovkého bracketu
        parent_source_round= self.placement_rounds[parent_name].get("source_main_round")

        # Vytvoření nového bracketu v placement_rounds
        self.placement_rounds[new_name]= {
            "ranks": new_ranks,
            "matches": sub_matches,
            "processed": False,
            "source_main_round": parent_source_round
        }
        print(f"DEBUG: Vytvořen pod-pavout {new_name} pro {side}")

    def _finalize_ranking_positions(self,bracket_name: str,results: dict):
        """
        Ukončí dohrávku, zpracuje finální výsledky a přiřadí hráčům konečné umístění.
        """
        if bracket_name in self.placement_rounds:
            bracket_data = self.placement_rounds[bracket_name]
            bracket_data["processed"]= True

            # Pokud máme v posledním zápase dohrávky určeného vítěze,
            # uložíme ho přímo do struktury, aby Results.compute_final_ranking snadno našel.

            matches = bracket_data["matches"]
            if matches and len(matches) == 1:
                bracket_data["winner"] = matches[0].winner


            print(f"DEBUG: Dohrávka {bracket_name} byla uspěšně finalizována.")


