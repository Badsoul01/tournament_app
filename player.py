class Player:
    """
    Třída reprezentující hráče turnaje.
    Uchovává jeho iudentitu,příslušnost ke skupině, umístění a statistiky v jednotlivých fázích
    """
    def __init__(self,name: str) -> None:
        self.name: str = name
        self.group_name: str | None = None
        self.group_rank: int | None = None
        self.stats: dict = {}

    def _ensure_stage(self,stage_name: str) -> None:
        """
        Zajistí, že pro danou fázi turnaje existují ve statistice výchozí hodnoty.
        """
        if stage_name not in self.stats:
            self.stats[stage_name] = {
                "balls_win": 0,
                "balls_lost": 0,
                "games_win": 0,
                "games_lost": 0,
                "points": 0
            }

    def write_result(
            self,
            tournament_stage: str,
            balls_win: int,
            balls_lost: int,
            games_win: int,
            games_lost: int,
            points: int=0
    ) -> None:
        """
        Zapíše nebo přičte výsledky zápasu do statistik pro kontrétní fázi turnnaje.
        """
        self._ensure_stage(tournament_stage)
        s = self.stats[tournament_stage]
        s["balls_win"] +=balls_win
        s["balls_lost"] +=balls_lost
        s["games_win"] += games_win
        s["games_lost"] += games_lost
        s["points"] += points

    def difference_of_score(self,tournament_stage: str) -> dict[str, int]:
        """
        Vrátí rozdíl skóre (míčků i setů) pro danou fázi turnaje.
        """
        if tournament_stage not in self.stats:
            return {"Balls":0, "Games":0}

        s = self.stats[tournament_stage]

        return {
            "Balls":s["balls_win"]-s["balls_lost"],
            "Games":s["games_win"]- s["games_lost"]
        }

    def get_sorting_stats(self,stage_name: str) -> tuple[int, int, int]:
        """
        Vrátí n-tici statistik (body, rozdíl setů, rozdíl míčků)
        používanou pro řazení a porovnávání hráčů v tabulce.
        """
        if stage_name not in self.stats:
            return (0,0,0)
        s = self.stats[stage_name]
        diff = self.difference_of_score(stage_name)

        return (
            s.get("points",0),
            diff["Games"],
            diff["Balls"]
        )