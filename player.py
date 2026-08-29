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
        query = MatchModel.query.filter(
            MatchModel.is_finished == True,
            or_(MatchModel.player_a_id == player_id, MatchModel.player_b_id == player_id)
        )

        if stage_name == "minigroup":
            # Pro minitabulku bereme výhradně zápasy, které mají vyplněný bracket_id (patří do útěchy)
            query = query.filter(MatchModel.bracket_id.isnot(None))
        elif stage_name == "Group":
            # Pro základní skupiny bereme výhradně zápasy s group_id
            query = query.filter(MatchModel.group_id.isnot(None))

        finished_matches = query.all()

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

            p_games = 0
            opp_games = 0

            # Projdeme sety z nové relace (např. m.results nebo m.match_results)
            if hasattr(m, 'sets') and m.sets:
                for s in m.sets:
                    ba, bb = s.score_a, s.score_b

                    # Sčítání míčků
                    balls_win += ba if is_player_a else bb
                    balls_lost += bb if is_player_a else ba

                    # Sčítání vyhraných setů (zda set vyhrál hráč A nebo B)
                    if ba > bb:
                        if is_player_a:
                            p_games += 1
                        else:
                            opp_games += 1
                    elif bb > ba:
                        if not is_player_a:
                            p_games += 1
                        else:
                            opp_games += 1

            games_win += p_games
            games_lost += opp_games

            if p_games > opp_games:
                points += 3
            elif p_games == opp_games:
                points += 1

        # 4. Uložení výsledků do objektu statistik
        stats.points = points
        stats.games_win = games_win
        stats.games_lost = games_lost
        stats.balls_win = balls_win
        stats.balls_lost = balls_lost

        db.session.commit()

        print(f"DEBUG: Statistiky pro hráče ID {player_id} byly bleskově přepočítány.")