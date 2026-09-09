from app.models.models import db, Match as MatchModel,GroupStats as GroupStatsModel,ConsolationStats as ConsolationStatsModel,PlayoffStats as PlayoffStatsModel, \
    GlobalPlayer as GlobalPlayerModel, Player as PlayerModel, Bracket as BracketModel
from sqlalchemy import or_

class PlayerHelper:
    """
    Pomocná třída pro správu statistik a výpočtů nad databázovým modelem hráče.
    """

    @staticmethod
    def get_or_create_group_stats(player_id: int) -> GroupStatsModel:
        """Zajistí, že pro daného hráče existují záznamy statistik ve skupině."""
        stats = GroupStatsModel.query.filter_by(player_id=player_id).first()
        if not stats:
            stats = GroupStatsModel(player_id=player_id, points=0, games_win=0, games_lost=0,
                               balls_win=0, balls_lost=0)
            db.session.add(stats)
            db.session.commit()
        return stats

    @staticmethod
    def get_or_create_playoff_stats(player_id: int) -> PlayoffStatsModel:
        """Zajistí, že pro daného hráče existují záznamy statistik v playoff."""
        stats = PlayoffStatsModel.query.filter_by(player_id=player_id).first()
        if not stats:
            stats = PlayoffStatsModel(player_id=player_id)
            db.session.add(stats)
            db.session.commit()
        return stats

    @staticmethod
    def get_or_create_consolation_stats(player_id: int) -> ConsolationStatsModel:
        """Zajistí, že pro daného hráče existují záznamy statistik v útěše."""
        stats = ConsolationStatsModel.query.filter_by(player_id=player_id).first()
        if not stats:
            stats = ConsolationStatsModel(player_id=player_id, points=0, games_win=0, games_lost=0,
                                     balls_win=0, balls_lost=0)
            db.session.add(stats)
            db.session.commit()
        return stats

    @staticmethod
    def set_final_rank(player_id: int, rank: int, total_advancers: int, stage_name: str = "main"):
        """
        Zapíše finální umístění hráče do PlayoffStats (nebo ConsolationStats)
        a spočítá body do celkového žebříčku.
        """
        player = PlayerModel.query.get(player_id)
        if not player:
            return

        if stage_name == "main":
            stats = PlayerHelper.get_or_create_playoff_stats(player_id)
            stats.final_rank = rank

            # BODOVÁNÍ pro hlavní pavouk
            if rank <= total_advancers:
                base_points = (total_advancers - rank + 1)
                bonus = 0
                if rank == 1:
                    bonus = 3
                elif rank == 2:
                    bonus = 2
                elif rank == 3:
                    bonus = 1

                gained_points = base_points + bonus
                stats.points_gained = gained_points

        elif stage_name == "consolation":
            stats = PlayerHelper.get_or_create_consolation_stats(player_id)
            stats.final_rank = rank

        db.session.commit()

    @staticmethod
    def difference_of_score(player_id: int, tournament_stage: str) -> dict[str, int]:
        """Vrátí rozdíl skóre podle faktu, zda jde o skupinu nebo útěchu/minitabulku."""
        if tournament_stage == "Group":
            stats = GroupStatsModel.query.filter_by(player_id=player_id).first()
        elif tournament_stage in ["consolation", "minigroup"]:
            stats = ConsolationStatsModel.query.filter_by(player_id=player_id).first()
        else:
            stats = None

        if not stats or not hasattr(stats, 'balls_win'):
            return {"Balls": 0, "Games": 0}

        return {
            "Balls": stats.balls_win - stats.balls_lost,
            "Games": stats.games_win - stats.games_lost
        }

    @staticmethod
    def get_sorting_stats(player_id: int, stage_name: str) -> tuple[int, int, int]:
        """Vrátí n-tici statistik pro řazení v tabulce."""
        if stage_name == "Group":
            stats = GroupStatsModel.query.filter_by(player_id=player_id).first()
        else:
            stats = ConsolationStatsModel.query.filter_by(player_id=player_id).first()

        if not stats:
            return 0, 0, 0

        diff = PlayerHelper.difference_of_score(player_id, stage_name)
        return (
            stats.points,
            diff["Games"],
            diff["Balls"]
        )

    @staticmethod
    def recalculate_player_stats(player_id: int, stage_name: str) -> None:
        """Kompletně přepočítá statistiky hráče do příslušné tabulky podle fáze."""
        if stage_name == "Group":
            stats = PlayerHelper.get_or_create_group_stats(player_id)
        elif stage_name in ["consolation", "minigroup"]:
            stats = PlayerHelper.get_or_create_consolation_stats(player_id)
        else:
            # Hlavní playoff
            stats = PlayerHelper.get_or_create_playoff_stats(player_id)

        query = MatchModel.query.filter(
            MatchModel.is_finished == True,
            or_(MatchModel.player_a_id == player_id, MatchModel.player_b_id == player_id)
        )

        if stage_name == "minigroup":
            query = query.filter(MatchModel.bracket_id.isnot(None))
        elif stage_name == "Group":
            query = query.filter(MatchModel.group_id.isnot(None))
        elif stage_name == "main":
            # Pro hlavní pavouk filtrujeme zápasy v hlavním bracketu (kde bracket není útěcha)
            query = query.join(BracketModel, MatchModel.bracket_id == BracketModel.id) \
                .filter(BracketModel.is_consolation == False)

        finished_matches = query.all()

        if not finished_matches:
            if hasattr(stats, 'points'):
                stats.points = 0
            stats.games_win = 0
            stats.games_lost = 0
            stats.balls_win = 0
            stats.balls_lost = 0
            db.session.commit()
            return

        points = 0
        games_win = 0
        games_lost = 0
        balls_win = 0
        balls_lost = 0

        for m in finished_matches:
            is_player_a = (m.player_a_id == player_id)
            p_games = 0
            opp_games = 0

            if hasattr(m, 'sets') and m.sets:
                for s in m.sets:
                    ba, bb = s.score_a, s.score_b
                    balls_win += ba if is_player_a else bb
                    balls_lost += bb if is_player_a else ba

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

            if hasattr(stats, 'points'):
                if p_games > opp_games:
                    points += 3
                elif p_games == opp_games:
                    points += 1

        if hasattr(stats, 'points'):
            stats.points = points
        stats.games_win = games_win
        stats.games_lost = games_lost
        stats.balls_win = balls_win
        stats.balls_lost = balls_lost

        db.session.commit()
        print(f"DEBUG: Statistiky pro hráče ID {player_id} ({stage_name}) byly přepočítány.")