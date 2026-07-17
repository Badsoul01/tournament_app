
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

    def _create_matches_for_round(self,players_to_pair:list,tournament, is_snake_seeding=False):
        if is_snake_seeding:
            match_counter = 1
            half = len(players_to_pair) //2
            first_half = players_to_pair[:half]
            second_half = players_to_pair[half:]
            second_half.reverse()

            matches = []
            for player_a,player_b in zip(first_half,second_half):
                new_match = Match(
                    player_a=player_a,
                    player_b=player_b,
                    match_format=self.match_format,
                    tournament_stage=self.stage_name,
                    match_id=tournament.get_next_match_id(),

                )
                matches.append(new_match)
                match_counter+=1

            return matches

        matches = []

        work_players = list(players_to_pair)
        if len(work_players)%2 !=0:
            work_players.append(None)

        for i in range(0,len(work_players),2):
            player_a = players_to_pair[i]
            player_b = players_to_pair[i+1]
            if player_a is None:
                player_a,player_b = player_b,player_a

            new_match = Match(
                player_a=player_a,
                player_b=player_b,
                match_format=self.match_format,
                tournament_stage=self.stage_name,
                match_id=tournament.get_next_match_id()
            )
            if player_b is None:
                new_match.winner= player_a
                new_match.is_finished = True

            matches.append(new_match)

        return matches


    def generate_first_round(self,tournament):
        sorted_players = sorted(self.players, key=lambda p: p.get_sorting_stats("Group"), reverse=True)
        number_of_byes = self._calculating_byes()

        self.waiting_room = sorted_players[:number_of_byes]
        player_to_match = sorted_players[number_of_byes:]

        self.round_one_players=Group.apply_snake_seeding(player_to_match)
        matches = self._create_matches_for_round(self.round_one_players,is_snake_seeding=True,tournament=tournament)



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
                "matches": self._create_matches_for_round(current_losers,is_snake_seeding=False,tournament=tournament),
                "processed": False
            }
            print(f"DEBUG: Pridavam dohrávku {bracket_name}, aktualni stav: {self.placement_rounds}")


        players_for_next_round = advancing_players

        if len(players_for_next_round) ==1:
            self.winner = players_for_next_round[0]
            return []

        next_round_matches = self._create_matches_for_round(players_for_next_round,is_snake_seeding=False,tournament=tournament)
        self.current_round_number+=1
        self.rounds[self.current_round_number]= next_round_matches

        return next_round_matches


    def process_placement_bracket(self,bracket_name: str,tournament):
        #1.získání dat o bracketu
        bracket_data = self.placement_rounds[bracket_name]
        matches = bracket_data["matches"]
        low,high=bracket_data["ranks"]

        #2.sběr výsledků
        winners = [m.winner for m in matches if m.winner is not None]
        losers = [m.loser for m in matches if m.loser is not None]

        #3.Zastavovací podmínka (Base Case)
        # pokud je jen jeden zápas je konec
        if len(matches)== 1:
            print(f"umístění určeno: {low}.místo {winners[0].name},{high}.místo {losers[0].name}")
            return



        #4.Rekurzivní krok (pokud máme více zápasů, rozdělíme je)
        midpoint = low + (len(matches)//2)-1
        #Vytvoření horního pod-pavouka
        if len(winners)>1:
            win_bracket_name = f"{low}-{midpoint}"
            self.placement_rounds[win_bracket_name] = {
                "ranks": (low, midpoint),
                "matches": self._create_matches_for_round(winners,tournament=tournament),
                "processed":False
            }

        # Vytvoření dolního pod-pavouka
        if len(losers)>1:
            lose_bracket_name = f"{midpoint+1}-{high}"
            self.placement_rounds[lose_bracket_name] = {
                "ranks":(midpoint+1,high),
                "matches": self._create_matches_for_round(losers,tournament=tournament),
                "processed": False
            }


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



