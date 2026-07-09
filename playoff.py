from match import Match


class Playoff:

    def __init__(self,qualified_players:list,match_format:str):
        self.tournament_stage = "playoff"
        self.players = qualified_players
        self.match_format = match_format
        self.waiting_room = []
        self.round_one_players = []
        self.advancing_players = []
        self.eliminated_players = []
        self.current_round_number = 1
        self.rounds = {}
        self.winner = None

    def _calculating_byes(self):
        total_players = len(self.players)
        size_of_bracket = 2

        while size_of_bracket < total_players:
            size_of_bracket *= 2

        return size_of_bracket - total_players

    def _create_matches_for_round(self,players_to_pair:list):
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
                tournament_stage=self.tournament_stage
            )
            matches.append(new_match)

        return matches

    def generate_first_round(self):
        number_of_byes = self._calculating_byes()

        self.waiting_room = self.players[:number_of_byes]
        self.round_one_players = self.players[number_of_byes:]

        matches = self._create_matches_for_round(self.round_one_players)
        self.rounds[self.current_round_number] = matches


    def generate_next_round(self, played_matches:list):
        advancing_players = []
        self.eliminated_players[self.current_round_number] = []
        for match in played_matches:
            if match.winner is not None:
                advancing_players.append(match.winner)
                self.eliminated_players[self.current_round_number].append(match.losser)

        if self.waiting_room:
            players_for_next_round = self.waiting_room + advancing_players
            self.waiting_room = []
        else:
            players_for_next_round = advancing_players

        if len(players_for_next_round) ==1:
            self.winner = players_for_next_round[0]
            return []

        next_round_matches = self._create_matches_for_round(players_for_next_round)
        self.current_round_number+=1
        self.rounds[self.current_round_number]= next_round_matches

        return next_round_matches


