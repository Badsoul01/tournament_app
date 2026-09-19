from app.models.models import Tournament as TournamentModel, Player as PlayerModel, PlayoffStats as PlayoffStatsModel, \
    ConsolationStats as ConsolationStatsModel, GlobalPlayer as GlobalPlayerModel

def get_recent_finished_tournaments(limit=5):
    """Vrátí posledních N dokončených turnajů."""
    return (
        TournamentModel.query
        .filter_by(is_finished=True)
        .order_by(TournamentModel.date.desc(), TournamentModel.id.desc())
        .limit(limit)
        .all()
    )

def get_available_players_from_tournament(tournament_id, wizard):
    """
    Vytáhne hráče ze zadaného turnaje a vyfiltruje ty,
    kteří už jsou v aktualním wizardu zadáni.[cite: 8]
    """
    # 1. Hráči vybraného turnaje z DB[cite: 8]
    old_tournament = TournamentModel.query.get(tournament_id)
    if not old_tournament:
        return []

    # 2. Seznam jmen ze starého turnaje[cite: 8]
    old_player_names = [p.name for p in old_tournament.players]

    # 3. Jméno aktuálně v průvodci[cite: 8]
    current_names = wizard.get_all_current_player_names()

    # 4. Vracíme pouze jména, která ještě v průvodci nejsou[cite: 8]
    return [name for name in old_player_names if name not in current_names]


def get_players_ranking_map(criterion="last_tournament"):
    """
    Vrátí slovník {jméno hráče: hodnota_pro_seřazení}.
    Čím NIŽŠÍ hodnota, tím lepší hráč.[cite: 8]
    """
    ranking_map = {}
    if criterion == "last_tournament":
        # 1. Najdeme poslední dokončený turnaj[cite: 8]
        last_t = TournamentModel.query.filter_by(is_finished=True) \
            .order_by(TournamentModel.date.desc(), TournamentModel.id.desc()) \
            .first()
        if last_t:
            # Vytáhneme všechny hráče z tohoto turnaje
            players = PlayerModel.query.filter_by(tournament_id=last_t.id).all()

            for player in players:
                # Zjistíme finální umístění z PlayoffStats nebo ConsolationStats
                playoff_stats = PlayoffStatsModel.query.filter_by(player_id=player.id).first()
                consolation_stats = ConsolationStatsModel.query.filter_by(player_id=player.id).first()

                final_rank = None
                if playoff_stats and playoff_stats.final_rank is not None:
                    final_rank = playoff_stats.final_rank
                elif consolation_stats and consolation_stats.final_rank is not None:
                    final_rank = consolation_stats.final_rank

                if final_rank is not None:
                    ranking_map[player.name.strip().title()] = final_rank

    elif criterion == "global_rank":
        # 2. Vytáhneme body z GlobalPlayer (obracíme znaménko pro správné řazení)[cite: 8]
        global_list = GlobalPlayerModel.query.all()
        for g in global_list:
            ranking_map[g.name.strip().title()] = -g.total_points

    return ranking_map