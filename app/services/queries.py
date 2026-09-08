from app.models.models import  Tournament as TournamentModel, Player as PlayerModel, PlayerStats as PlayerStatsModel, GlobalPlayer as GlobalPlayerModel

def get_recent_finished_tournaments(limit=5):
    """Vrátí posledních N dokončených turnajů."""
    return (
        TournamentModel.query
        .filter_by(is_finished=True)
        .order_by(TournamentModel.date.desc(), TournamentModel.id.desc())
        .limit(limit=limit)
        .all()
    )

def get_available_players_from_tournament(tournament_id,wizard):
    """
    Vytáhne hráče ze zadaného turnaje a vyfiltruje ty,
    kteří už jsou v aktualním wizardu zadáni.
    """

    # 1. Hráči vybraného turnaje z DB
    old_tournament = TournamentModel.query.get(tournament_id)
    if not old_tournament:
        return []

    #  2. Seznam jmen ze starého turnaje
    old_player_names = [p.name for p in old_tournament.players]

    # 3. Jméno aktuálně v průvodci
    current_names = wizard.get_all_current_player_names()

    #4 Vracíme pouze jména, která ještě v průvodci nejsou
    return [name for name in old_player_names if name not in current_names]

def get_players_ranking_map(criterion="last_tournament"):
    """
    Vrátí slovník {jméno hráče: hodnota_pro_seřazení}.
    Čím NIŽŠÍ hodnot, tím lepší hráč.
    """
    ranking_map = {}
    if criterion == "last_tournament":
        # 1. Najdeme poslední dokončený turnaj
        last_t = TournamentModel.query.filter_by(is_finished=True)\
                                .order_by(TournamentModel.date.desc(), TournamentModel.id.desc())\
                                .first()
        if last_t:
            stats = PlayerStatsModel.query.join(PlayerModel)\
                                    .filter(PlayerModel.tournament_id== last_t.id)\
                                    .filter(PlayerStatsModel.final_rank.isnot(None))\
                                    .all()

            for s in stats:
                ranking_map[s.player.name.strip().title()] = s.final_rank
    elif criterion == "global_rank":
        # 2. Vytáhneme body z GlobalPLayer (obracíme znaménko pro správné řazení)
        global_list = GlobalPlayerModel.query.all()
        for g in global_list:
            ranking_map[g.name.strip().title()] = -g.total_points

    return ranking_map