class Player:

    def __init__(self,name):
        self.name = name
        self.group= {
            "balls_win": 0,
            "balls_lost": 0,
            "games_win": 0,
            "games_lost": 0,
            "points": 0
        }
        self.playoff = {
                "balls_win": 0,
                "balls_lost": 0,
                "games_win": 0,
                "games_lost": 0,
                "points": 0
            }

    def write_result(self,tournament_stage:str,balls_win,balls_lost,games_win,games_lost,points=None):
        if tournament_stage ==  "Group":
            self.group["balls_win"] +=balls_win
            self.group["balls_lost"] +=balls_lost
            self.group["games_win"] += games_win
            self.group["games_lost"] += games_lost
            self.group["points"] += points

        elif tournament_stage == "Playoff":
            self.playoff["balls_win"] += balls_win
            self.playoff["balls_lost"] += balls_lost
            self.playoff["games_win"] += games_win
            self.playoff["games_lost"] += games_lost



    def difference_of_score(self,tournament_stage:str):
        difference_of_balls = 0
        difference_of_games = 0

        if tournament_stage == "Group":
            difference_of_balls = self.group["balls_win"] - self.group["balls_lost"]
            difference_of_games = self.group["games_win"] - self.group["games_lost"]

        elif tournament_stage == "Playoff":
            difference_of_balls = self.playoff["balls_win"] - self.playoff["balls_lost"]
            difference_of_games = self.playoff["games_win"] - self.playoff["games_lost"]

        return difference_of_balls,difference_of_games

