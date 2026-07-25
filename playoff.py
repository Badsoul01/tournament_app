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

    def generate_first_round(self,tournament) -> None:
        """
        Vygeneruje 1.kolo playoff včetně nasazení hráčů,
        výpočtu volných losů (BYE) a chytrého proházení pavouka.
        """
        #1. Seřadíme hráče podle statistik ve skupině sestupně
        sorted_players = sorted(self.players, key=lambda p: p.get_sorting_stats("Group"), reverse=True)
        number_of_byes = self._calculating_byes()

        # Cílený výběr do waiting_room: primárně vítězové skupin
        group_winners = [p for p in sorted_players if getattr(p,"group_rank", None) == 1]
        other_players = [p for p in sorted_players if getattr(p,"group_rank", None) != 1]

        #. Rozdělení na hráče s volným losem (BYE) a ty, co hrají pvní kolo
        waiting_room =  group_winners[:number_of_byes]
        if len(waiting_room) < number_of_byes:
            remaining_needed = number_of_byes - len(waiting_room)
            waiting_room.extend(other_players[:remaining_needed])

        self.waiting_room = waiting_room
        waiting_set = set(self.waiting_room)
        players_to_match = [p for p in sorted_players if p not in waiting_set]

        # Vytvoření základních dvojic a jejich úprava přes novou pomocnou metodu
        matches = self._create_matches_for_round(players=players_to_match,tournament=tournament)
        matches = self._reorder_matches_for_spread(matches)

        # Vytvoříme BYE Zápasů pro nejlepší hráče z waiting_room)
        bye_matches_top = []
        bye_matches_bottom = []

        for i, player in enumerate(self.waiting_room):
            bye_match = Match(
                player_a=player,
                player_b=None,
                match_format=self.match_format,
                tournament_stage=self.stage_name,
                match_id=tournament.get_next_match_id())

            bye_match.winner = player
            bye_match.is_finished = True

            # Strategické umístění BYE slotů na okraje pavouka (začátek a konec),
            # aby netvořily blok hned pod sebou s hlavními nasazenými hráči.
            if i % 2 == 0:
                bye_matches_top.append(bye_match)
            else:
                bye_matches_bottom.append(bye_match)

        # Strategické umístění BYE slotů na okraje pavouka (začátek a konec)
        matches = bye_matches_top + matches + bye_matches_bottom

        self.rounds[self.current_round_number]= matches
        self.waiting_room = []



    def generate_next_round(self, played_matches:list,tournament) -> list:
        """
        Vygeneruje následující kolo playoff na základě dohraných zápasů předchozího kola,
        vyhodnotí postupující, poražené a případně založí větve pro dohrávky o umístění.
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

            total_slots = len(self.players)
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

        self.current_round_number+=1
        self.rounds[self.current_round_number]= next_round_matches

        return next_round_matches

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

    def check_and_proceed(self,tournament) -> bool:
        """
        Zkontroluje stav aktuálního kola hlavního poavouka i všech dohrávek
        a v případě dohrání automaticky vygeneruje kolo následující.
        """
        #kontrola hlavního pavouka
        current_matches = self.rounds.get(self.current_round_number,[])
        main_advance = False


        if current_matches and all(m.is_finished for m in current_matches):
            if (self.current_round_number + 1) not in self.rounds:
                self.generate_next_round(current_matches,tournament=tournament)
                main_advance= True

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

    # ==========================================
    # INTERNÍ POMOCNÉ METODY (PRIVÁTNÍ)
    # ==========================================

    def _calculating_byes(self) -> int:
        """
        Spočítá počet potřebných volných lusů(BYE) do nejbližší mocniny dvou.
        """

        total_players = len(self.players)
        size_of_bracket = 2

        while size_of_bracket < total_players:
            size_of_bracket *= 2

        return size_of_bracket - total_players

    def _create_matches_for_round(self,players: list,tournament)-> list:
        """
        Pomocná metoda pro vytvoření zápasů v kole metodou párování (1. vs posledního).
        """

        #Použijeme seeding metodu
        seeded = self.get_seeded_players(players=players,advance_per_group=tournament.advance_per_group)
        matches = []
        #párování první s posledním, druhý s předposledním
        # s osmi hráči, spáruje indexi (0,7),(1,6)
        for i in range(len(seeded) // 2):
            player_A = seeded[i]
            player_B = seeded[len(seeded) -1-i]

            match = Match(player_a=player_A,
                          player_b=player_B,
                          match_format=self.match_format,
                          tournament_stage=self.stage_name,
                          match_id=tournament.get_next_match_id()
                          )
            matches.append(match)

        return matches

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

    def _reorder_matches_for_spread(self,matches: list) -> list:
        """
        Chytře přeuspořádá zápavy v prvním kole, aby se top hráči nepotkali příliš brzo.
        """
        if len(matches)<4:
            return matches

        half = len(matches) //2
        top_half = matches[:half]
        bottom_half = matches[half:]
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
                    reordered[j], reordered[i + 1] = reordered[i + 1], reordered[j]
            return reordered





