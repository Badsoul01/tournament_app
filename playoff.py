
from match import Match
from group import Group
from config import PLAYOFF_RULES



class Playoff:

    def __init__(self,qualified_players:list,match_format:str,stage_name:str,playoff_elimination_action):
        self.stage_name= stage_name
        self.players = qualified_players
        self.match_format = match_format
        self.waiting_room = []
        self.round_one_players = []
        self.eliminated_players = {}
        self.current_round_number = 1
        self.rounds = {}
        self.winner = None

        self.playoff_elimination_action = playoff_elimination_action
        self.placement_rounds = {}


    def _calculating_byes(self):
        total_players = len(self.players)
        size_of_bracket = 2

        while size_of_bracket < total_players:
            size_of_bracket *= 2

        return size_of_bracket - total_players

    def _create_matches_for_round(self,players,tournament):
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


    def generate_first_round(self,tournament):

        sorted_players = sorted(self.players, key=lambda p: p.get_sorting_stats("Group"), reverse=True)
        number_of_byes = self._calculating_byes()

        self.waiting_room = sorted_players[:number_of_byes]
        players_to_match = sorted_players[number_of_byes:]


        matches = self._create_matches_for_round(players=players_to_match,tournament=tournament)



        for i, player in enumerate(self.waiting_room):
            bye_match = Match(
                player_a=player,
                player_b=None,
                match_format=self.match_format,
                tournament_stage=self.stage_name,
                match_id=tournament.get_next_match_id())

            bye_match.winner = player
            bye_match.is_finished= True


            if i%2 == 0:
                matches.insert(0,bye_match)
            else:
                matches.append(bye_match)

        self.rounds[self.current_round_number] = matches
        self.waiting_room = []


    def generate_next_round(self, played_matches:list,tournament):
        advancing_players = []
        current_losers=[]

        self.eliminated_players[self.current_round_number] = []

        for match in played_matches:
            if match.is_finished and  match.winner is not None:
                advancing_players.append(match.winner)
                if match.player_A is not None and match.player_B is not None:
                    loser=match.player_B if match.winner== match.player_A else match.player_A
                    current_losers.append(loser)


        self.eliminated_players[self.current_round_number] = current_losers


        if self.playoff_elimination_action == "consolation" and len(current_losers)>=2:
            all_previously_eliminated = sum(len(v) for k,v in self.eliminated_players.items() if k< self.current_round_number)

            total_slots = len(self.players)
            start_rank = (total_slots - (all_previously_eliminated+ len(current_losers))) + 1
            end_rank = total_slots - all_previously_eliminated
            bracket_name = f"{start_rank}-{end_rank}"



            self.placement_rounds[bracket_name] = {
                "ranks":(start_rank,end_rank),
                "matches": self._create_matches_for_round(current_losers,tournament=tournament),
                "processed": False
            }
            print(f"DEBUG: Pridavam dohrávku {bracket_name}, aktualni stav: {self.placement_rounds}")


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


    def process_placement_bracket(self,bracket_name: str,tournament):
        """Hlavní řídící metoda pro dohrávky"""
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
        if len(results["winners"]) > 1:
            self._create_sub_bracket(bracket_name,results["winners"], "winners",tournament)
        if len(results["losers"]) > 1:
            self._create_sub_bracket(bracket_name,results["losers"], "losers",tournament)

    def _get_bracket_results(self,matches):
        """Pomocná metoda pro sběr vítězů a poražených"""
        return {
            "winners": [m.winner for m in matches if m.winner is not None],
            "losers": [m.loser for m in matches if m.loser is not None]
        }

    def _create_sub_bracket(self,parent_name,players,side,tournament):
        """
        Vytvoří pod-pavouka na základě výsledků předchozího kola.
        side: "winners" nebo "losers"
        """

        # Získání původních rozsahů
        low,high = self.placement_rounds[parent_name]["ranks"]
        midpoint = low + (len(players)*2 //2) -1

        if side == "winners":
            new_ranks = (low,midpoint)
            new_name = f"{low}-{midpoint}"
        else:
            new_ranks = (midpoint+1, high)
            new_name = f"{midpoint+1}-{high}"

        if new_name in self.placement_rounds:
            print(f"DEBUG: Pod-pavouk {new_name} již existuje,přeskakuji tvorbu")
            return

        # Vytvoření nového bracketu v placement_rounds
        self.placement_rounds[new_name]= {
            "ranks": new_ranks,
            "matches": self._create_matches_for_round(players=players,tournament=tournament),
            "processed": False
        }
        print(f"DEBUG: Vytvořen pod-pavout {new_name} pro {side}")


    def get_seeded_players(self,players,advance_per_group):
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

    def get_sorted_placement_rounds(self):
        return sorted(self.placement_rounds.items(), key=lambda x: x[1]["ranks"][0],reverse=True)

    def _finalize_ranking_positions(self,bracket_name,results):
        """Ukončí dohrávku a označí jí za zpracovanou."""
        if bracket_name in self.placement_rounds:
            self.placement_rounds[bracket_name]["processed"]= True
            print(f"DEBUG: Dohrávka {bracket_name} byla uspěšně finalizována.")


    def check_and_proceed(self,tournament):
        #kontrola hlavního pavouka
        current_matches = self.rounds.get(self.current_round_number,[])
        main_advance = False

        if current_matches and all(m.is_finished for m in current_matches):
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




