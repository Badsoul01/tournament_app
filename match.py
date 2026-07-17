from player import Player

class Match:

    def __init__(self, player_a:Player,player_b:Player,match_format:str, tournament_stage:str,match_id):
        self.player_A = player_a
        self.player_B = player_b
        self.match_format = match_format
        self.tournament_stage = tournament_stage
        self.match_id = match_id
        self.winner = None
        self.loser = None
        self.is_finished = False
        self.played_sets=[]

    def evaluate_match(self,played_sets:list[tuple]):
        self.played_sets = played_sets
        player_a = {
            "games_win":0,
            "games_lost":0,
            "balls_win":0,
            "balls_lost":0,
            "points":0
        }
        player_b = {
            "games_win": 0,
            "games_lost": 0,
            "balls_win": 0,
            "balls_lost": 0,
            "points":0
        }

        for balls_a,balls_b in played_sets:
            player_a["balls_win"]+=balls_a
            player_a["balls_lost"] +=balls_b
            player_b["balls_win"] += balls_b
            player_b["balls_lost"] += balls_a

            if balls_a > balls_b:
                player_a["games_win"] += 1
                player_b["games_lost"] += 1
            else:
                player_a["games_lost"] +=1
                player_b["games_win"] +=1

        if player_a["games_win"]>player_b["games_win"]:
            player_a["points"] +=3
            self.winner = self.player_A
            self.loser = self.player_B

        elif player_a["games_win"] == player_b["games_win"]:
            player_a["points"] +=1
            player_b["points"] +=1

        else:
            player_b["points"] +=3
            self.winner = self.player_B
            self.loser = self.player_A

        self.player_A.write_result(tournament_stage=self.tournament_stage,
                                   balls_win=player_a["balls_win"],
                                   balls_lost=player_a["balls_lost"],
                                   games_win=player_a["games_win"],
                                   games_lost=player_a["games_lost"],
                                   points=player_a["points"]
                                   )
        self.player_B.write_result(tournament_stage=self.tournament_stage,
                                   balls_win=player_b["balls_win"],
                                   balls_lost=player_b["balls_lost"],
                                   games_win=player_b["games_win"],
                                   games_lost=player_b["games_lost"],
                                   points=player_b["points"]
                                   )
        self.is_finished = True

        return self.is_finished
