from functools import total_ordering

import tournament
from match import Match
from group import Group
from config import PLAYOFF_RULES


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
        self.current_round_number: int = 1
        self.rounds: dict[int, list] = {}
        self.winner = None

        self.playoff_elimination_action: str = playoff_elimination_action
        self.placement_rounds: dict[str, dict] = {}

    # ==========================================
    # VEŘEJNÉ API (HLAVNÍ METODY)
    # ==========================================

    def generate_next_round(self, played_matches:list,tournament) -> list:
        """
        Vygeneruje následující kolo playoff na základě dohraných zápasů předchozího kola,
        využívá předpřipravé sloty v self.rounds a nahrazuje je reálnámi Match objekty
        """
        advancing_players = []
        current_losers=[]
        self.eliminated_players[self.current_round_number] = []

        # Pokud jsme v 1.kole, můžeme použít metodu pro zachování BYE pozic(None)
        if self.current_round_number == 1:
            current_losers = self.get_placement_losers_from_first_round(played_matches)

        for match in played_matches:
            if match.is_finished and  match.winner is not None:
                advancing_players.append(match.winner)
                if self.current_round_number >1:
                    if match.player_A is not None and match.player_B is not None:
                        loser=match.player_B if match.winner== match.player_A else match.player_A
                        current_losers.append(loser)

        self.eliminated_players[self.current_round_number] = current_losers

        if self.playoff_elimination_action == "consolation" and len([p for p in current_losers if p is not None]) >= 2:
            all_previously_eliminated = sum(len([p for p in v if p is not None]) for k,v in self.eliminated_players.items() if k < self.current_round_number)
            real_losers = [p for p in current_losers if p is not None]

            first_round_items = self.rounds.get(1,[])
            total_slots = len(first_round_items) *2
            start_rank = (total_slots - (all_previously_eliminated+ len(real_losers))) + 1
            end_rank = total_slots - all_previously_eliminated
            bracket_name = f"{start_rank}-{end_rank}"

            #Zde použijeme bezpečné vytvoření dohrávkových zápasů
            placement_matches = self._create_placement_bracket_matches(current_losers,tournament=tournament)

            self.placement_rounds[bracket_name] = {
                "ranks":(start_rank,end_rank),
                "matches": placement_matches,
                "processed": False
            }
            print(f"DEBUG: Přidávám dohrávku {bracket_name}, aktualní stav: {self.placement_rounds}")


        if len(advancing_players) ==1:
            self.winner = advancing_players[0]
            return []

        next_round_matches = []



        for i in range(0,len(advancing_players),2):
            match= Match(
                player_a=advancing_players[i],
                player_b=advancing_players[i+1] if i+1 <len(advancing_players) else None,
                match_format=self.match_format,
                tournament_stage=self.stage_name,
                match_id=tournament.get_next_match_id()
            )
            next_round_matches.append(match)


        return next_round_matches

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

    def generate_slotted_bracket(self,groups: dict,tournament,) -> list:
        """
        Vygeneruje strukturu prvního kola složenou čistě ze slotů("1A", "2B" apod).
        Funguje jako nezáslislá šablona pavouka pro budoucí nasazení hráčů.
        """
        # 1. Získáme surové sloty ze všech skupin
        all_slots = self._generate_slots(groups=groups, advance_per_group=tournament.advance_per_group)

        # 2.Využijeme dedikovanou metodu pro výpočet BYE podle počtu slotů
        number_of_byes = self._calculating_byes(len(all_slots))

        # 3. Oddělíme vítěze/první místo (začínající "1") jako prioritní pro BYE
        group_first = [slot for slot in all_slots if slot.startswith("1")]
        other_slots = [slot for slot in all_slots if not slot.startswith("1")]

        #4. waiting room pro volné losy
        waiting_room = group_first[:number_of_byes]
        if len(waiting_room) < number_of_byes:
            remaining_needed = number_of_byes - len(waiting_room)
            waiting_room.extend(other_slots[:remaining_needed])

        waiting_set = set(waiting_room)
        slots_to_match = [s for s in all_slots if s not in waiting_set]

        # 5. Spárování zbývajícíh slotů
        paired_slots = []
        for i in range(len(slots_to_match) // 2):
            slot_a = slots_to_match[i]
            slot_b = slots_to_match[len(slots_to_match)-1-i]
            paired_slots.append((slot_a,slot_b))

        paired_slots = self._reorder_matches_for_spread(paired_slots)

        #6. Umístění BYE dvojic (slot,None) na okraje pavouka
        bye_top = []
        bye_bottom = []

        for i, slot in enumerate(waiting_room):
            bye_pair = (slot, None)
            if i % 2 == 0:
                bye_top.append(bye_pair)
            else:
                bye_bottom.append(bye_pair)

        final_bracket_structure = bye_top + paired_slots + bye_bottom
        return final_bracket_structure

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
        #kontrola hlavního pavouka
        current_matches = self.rounds.get(self.current_round_number,[])
        main_advance = False
        # Porjdeme zápasy aktualního kola a průběžně posouváme vítěze do dalšího kola
        for idx, match in enumerate(current_matches):
            if match.is_finished and match.winner is not None:
                self.move_winner_to_next_round(
                    finished_match=match,
                    round_num=self.current_round_number,
                    match_index=idx,
                    tournament=tournament
                )

        # Kontrola, zda jsou hotové věechny zápasy aktuálního kola
        if current_matches and all(m.is_finished for m in current_matches):
            next_round_num = self.current_round_number + 1
            # Pokud existuje další kolo, vygenerujeme ho /posuneme se
            if next_round_num in self.rounds:
                # Pokud ještě nemáme v dalším kole vytvořené zápasy(nebo to jsou jen tuplové sloty,
                # které se nepřevedly), zavoláme generate_next_round
                self.current_round_number = next_round_num
                main_advance = True
            else:
                # Pokud další kolo neexistuje, znamená to, právě skončilo finále
                # vytáhneme vítěze z posledního zápasu finále.
                if len(current_matches) == 1:
                    self.winner = current_matches[0].winner
                    print(f"DEBUG: Turnaj má celkového vítěze: {self.winner}")


        #Kontrola dohrávky
        print(f"DEBUG: Počet placement_rounds: {len(self.placement_rounds)}")
        keys_to_process = [bracket_name for bracket_name in self.placement_rounds.keys()]
        for bracket_name in keys_to_process:
            data = self.placement_rounds[bracket_name]
            matches = data["matches"]

            for m in matches:
                print(f"DEBUG: Zápas ID {m.match_id} je hotov: {m.is_finished}")


            if all(m.is_finished for m in matches):
                print(f"DEBUG: Všechny zápasy v {bracket_name} jsou hotové, zpracovávám...")
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
        return sorted(self.placement_rounds.items(), key=lambda x: x[1]["ranks"][0],reverse=True)

    def generate_full_bracket_structure(self,groups: dict, tournament) -> None:
        """
        Vygeneruje strukturu celého pavouka:
        - 1. kolo zůstává jako slotové n-tice (čekájící na dohrání skupin a převod na Match).
        - 2. a další kolo se generují jako prázdné objekty Match s navázanými vazbami pro postup vítězů.
        """
        import math
        # KROK 1: vytvoříme první kolo pavouka podle metody generate_slotted_bracket
        slot_structure = self.generate_slotted_bracket(groups=groups, tournament=tournament)
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



    # ==========================================
    # INTERNÍ POMOCNÉ METODY (PRIVÁTNÍ)
    # ==========================================

    def _calculating_byes(self, total_slots: int) -> int:
        """
        Spočítá počet potřebných volných lusů(BYE) bez nutnosti znát hráče.
        """
        size_of_bracket = 2

        while size_of_bracket < total_slots:
            size_of_bracket *= 2

        return size_of_bracket - total_slots


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
        return {
            "winners": [m.winner for m in matches if m.winner is not None],
            "losers": [m.loser for m in matches if m.loser is not None]
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


        # Vytvoření nového bracketu v placement_rounds
        self.placement_rounds[new_name]= {
            "ranks": new_ranks,
            "matches": sub_matches,
            "processed": False
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

    def _reorder_matches_for_spread(self,items: list) -> list:
        """
        Chytře přeuspořádá zápavy v prvním kole, aby se top hráči nepotkali příliš brzo.
        """
        if len(items)<4:
            return items

        half = len(items) // 2
        top_half = items[:half]
        bottom_half = items[half:]
        bottom_half.reverse()

        reordered = []
        for j in range(max(len(top_half), len(bottom_half))):
            if j < len(top_half):
                reordered.append(top_half[j])
            if j < len(bottom_half):
                reordered.append(bottom_half[j])

            # Prohození v blocích
            for i in range(2, len(reordered) - 1, 4):
                if i + 1 < len(reordered):
                    reordered[i], reordered[i + 1] = reordered[i + 1], reordered[i]
        return reordered


    def _generate_slots(self,groups: dict,advance_per_group: int,start_from: int = 1) -> list:
        list_of_slots = []

        for group_name in groups:
            for num in range(start_from,start_from+advance_per_group):
                list_of_slots.append(f"{num}{group_name}")

        return list_of_slots



