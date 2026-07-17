class Player:

    def __init__(self,name):
        self.name = name
        self.stats= {}

    def _ensure_stage(self,stage_name):
        if stage_name not in self.stats:
            self.stats[stage_name] = {
                "balls_win": 0,
                "balls_lost": 0,
                "games_win": 0,
                "games_lost": 0,
                "points": 0
            }
    def write_result(self,tournament_stage,balls_win,balls_lost,games_win,games_lost,points=0):
        self._ensure_stage(tournament_stage)
        s = self.stats[tournament_stage]
        s["balls_win"] +=balls_win
        s["balls_lost"] +=balls_lost
        s["games_win"] += games_win
        s["games_lost"] += games_lost
        s["points"] += points


    def difference_of_score(self,tournament_stage):
        if tournament_stage not in self.stats:
            return {"Balls":0, "Games":0}

        s = self.stats[tournament_stage]

        return {
            "Balls":s["balls_win"]-s["balls_lost"],
            "Games":s["games_win"]- s["games_lost"]
        }

    def get_sorting_stats(self,stage_name):
        if stage_name not in self.stats:
            return (0,0,0)
        s = self.stats[stage_name]
        diff = self.difference_of_score(stage_name)

        return (
            s.get("points",0),
            diff["Games"],
            diff["Balls"]
        )