from player import Player

class Match:
    """
    Třída reprezentující jeden kontrétní zápas mezi dvěma hráči.
    Uchovává jeho stav, odehrané sety, vítěze a poraženého.
    """

    def __init__(
            self,
            player_a:Player,
            player_b:Player,
            match_format:str,
            tournament_stage:str,
            match_id: int | str,
            next_match: 'Match | None' = None,
            target_slot: str | None = None
    ) -> None:
        self.player_A: Player = player_a
        self.player_B: Player = player_b
        self.match_format: str = match_format
        self.tournament_stage: str = tournament_stage
        self.match_id: int | str = match_id

        self.next_match: Match | None = next_match
        self.target_slot: str | None = target_slot

        self.winner: Player | None = None
        self.loser: Player | None = None
        self.is_finished: bool = False
        self.played_sets: list[tuple[int, int]] = []

    def evaluate_match(self,played_sets:list[tuple[int,int]]) -> bool:
        """
         Vyhodnotí zápas na zákaladě odehraných setů:
         1. Spočítá skóre míčků a setů pro oba hráče.
         2. Určí vítěze, poraženého a body do tabulky.
         3. Propíše statistiky hráčům a označí zápas jako dohraný.
        """
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

        if self.next_match and self.winner:
            # Podle target_slot určíme, do kterého slotu v dalším zápase vítěz patří
            if self.target_slot == "A":
                self.next_match.player_A = self.winner
            elif self.target_slot == "B":
                self.next_match.player_B = self.winner

        return self.is_finished


