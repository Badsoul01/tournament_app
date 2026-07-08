class Player:

    def __init__(self,name):
        self.name = name
        self.group_stage = {
            "balls_win": 0,
            "balls_lost": 0,
            "games_win": 0,
            "games_lost": 0,
            "points": 0
        }
        self.playoff_stage = {
                "balls_win": 0,
                "balls_lost": 0,
                "games_win": 0,
                "games_lost": 0,
                "points": 0
            }

    def write_result(self,tournament_stage:str,balls_win,balls_lost,games_win,games_lost,points):
        if tournament_stage ==  "group_stage":
            self.group_stage["balls_win"] +=balls_win
            self.group_stage["balls_lost"] +=balls_lost
            self.group_stage["games_win"] += games_win
            self.group_stage["games_lost"] += games_lost
            self.group_stage["points"] += points

        elif tournament_stage == "playoff_stage":
            self.playoff_stage["balls_win"] += balls_win
            self.playoff_stage["balls_lost"] += balls_lost
            self.playoff_stage["games_win"] += games_win
            self.playoff_stage["games_lost"] += games_lost
            self.playoff_stage["points"] += points


    def difference_of_score(self,tournament_stage:str):
        difference_of_balls = 0
        difference_of_games = 0

        if tournament_stage == "group_stage":
            difference_of_balls = self.group_stage["balls_win"] - self.group_stage["balls_lost"]
            difference_of_games = self.group_stage["games_win"] - self.group_stage["games_lost"]

        elif tournament_stage == "playoff_stage":
            difference_of_balls = self.playoff_stage["balls_win"] - self.playoff_stage["balls_lost"]
            difference_of_games = self.playoff_stage["games_win"] - self.playoff_stage["games_lost"]

        return difference_of_balls,difference_of_games

