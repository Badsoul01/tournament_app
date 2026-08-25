from models import db, PlayerStats, Match as MatchModel
from sqlalchemy import func, or_

class PlayerHelper:
    """
    Pomocná třída pro správu statistik a výpočtů nad databázovým modelem hráče.
    """

    @staticmethod
    def get_or_create_stats(player_id: int, stage_name: str) -> PlayerStats:
        """Zajistí, že pro daného hráče a fázi existuje záznam statistik v DB."""
        stats = PlayerStats.query.filter_by(player_id=player_id, stage_name=stage_name).first()
        if not stats:
            stats = PlayerStats(player_id=player_id, stage_name=stage_name, points=0, games_win=0, games_lost=0,
                                balls_win=0, balls_lost=0)
            db.session.add(stats)
            db.session.commit()
        return stats

    @staticmethod
    def difference_of_score(player_id: int, tournament_stage: str) -> dict[str, int]:
        """Vrátí rozdíl skóre (míčků i setů) pro danou fázi turnaje z DB."""
        stats = PlayerStats.query.filter_by(player_id=player_id, stage_name=tournament_stage).first()
        if not stats:
            return {"Balls": 0, "Games": 0}

        return {
            "Balls": stats.balls_win - stats.balls_lost,
            "Games": stats.games_win - stats.games_lost
        }

    @staticmethod
    def get_sorting_stats(player_id: int, stage_name: str) -> tuple[int, int, int]:
        """Vrátí n-tici statistik (body, rozdíl setů, rozdíl míčků) pro řazení v tabulce."""
        stats = PlayerStats.query.filter_by(player_id=player_id, stage_name=stage_name).first()
        if not stats:
            return (0, 0, 0)

        diff = PlayerHelper.difference_of_score(player_id, stage_name)
        return (
            stats.points,
            diff["Games"],
            diff["Balls"]
        )

    @staticmethod
    def set_final_rank(player_id: int, rank: int, stage_name: str) -> None:
        """Uloží hráči jeho konečné umístění v turnaji do PlayerStats."""
        stats = PlayerHelper.get_or_create_stats(player_id, stage_name)
        stats.final_rank = rank
        db.session.commit()
        print(f"DEBUG: Hráč {player_id} dokončil turnaj na {rank}. místě!")

    @staticmethod
    def recalculate_player_stats(player_id: int, stage_name: str) -> None:
        """Kompletně přepočítá statistiky hráče pomocí rychlých SQL agregací."""

        stats = PlayerHelper.get_or_create_stats(player_id, stage_name)

        # 1. Zjistíme, zda je hráč vůbec v nějakých dohraných zápasech
        finished_matches = MatchModel.query.filter(
            MatchModel.is_finished == True,
            or_(MatchModel.player_a_id == player_id, MatchModel.player_b_id == player_id)
        ).all()

        if not finished_matches:
            stats.points = 0
            stats.games_win = 0
            stats.games_lost = 0
            stats.balls_win = 0
            stats.balls_lost = 0
            return

        # 2. Inicializace proměnných
        points = 0
        games_win = 0
        games_lost = 0
        balls_win = 0
        balls_lost = 0

        # 3. Rychlý průchod v paměti Pythonu nad hotovými daty
        for m in finished_matches:
            is_player_a = (m.player_a_id == player_id)

            p_games = m.score_a if is_player_a else m.score_b
            opp_games = m.score_b if is_player_a else m.score_a

            games_win += p_games
            games_lost += opp_games

            if p_games > opp_games:
                points += 3
            elif p_games == opp_games:
                points += 1

            if m.sets_data:
                for set_str in m.sets_data.split(","):
                    if ":" in set_str:
                        parts = set_str.split(":")
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            ba, bb = int(parts[0]), int(parts[1])
                            balls_win += ba if is_player_a else bb
                            balls_lost += bb if is_player_a else ba

        # 4. Uložení výsledků do objektu statistik
        stats.points = points
        stats.games_win = games_win
        stats.games_lost = games_lost
        stats.balls_win = balls_win
        stats.balls_lost = balls_lost

        print(f"DEBUG: Statistiky pro hráče ID {player_id} byly bleskově přepočítány.")