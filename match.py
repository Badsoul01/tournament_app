from models import db, Match as MatchModel
from player import PlayerHelper


def evaluate(match_id, player_a_games:list, player_b_games:list) -> bool:
    """
    Vyhodnotí zápas na základě odehraných setů:
    1. Spočítá skóre setů a míčků pro oba hráče.
    2. Určí vítěze, nebo ošetří remízu (winner_id = None).
    3. Uloží stav do databázového modelu zápasu.
    """
    if not player_a_games or not player_b_games:
        return False

    played_games = []
    for a, b in zip(player_a_games, player_b_games):
        if a != "" and b != "":
            played_games.append((int(a), int(b)))

    db_match = MatchModel.query.get_or_404(match_id)

    games_a_win = 0
    games_b_win = 0
    balls_a_total = 0
    balls_b_total = 0

    for balls_a, balls_b in played_games:
        balls_a_total += balls_a
        balls_b_total += balls_b

        if balls_a > balls_b:
            games_a_win += 1
        elif balls_b > balls_a:
            games_b_win += 1
        # Případné čisté 0:0 v setu můžeme ignorovat nebo ošetřit

    # Uložíme celkové skóre setů do modelu zápasu
    db_match.score_a = games_a_win
    db_match.score_b = games_b_win
    db_match.sets_data = ",".join([f"{a}:{b}" for a, b in played_games])

    points_a = 0
    points_b = 0

    # Určení vítěze / remízy
    if games_a_win > games_b_win:
        db_match.winner_id = db_match.player_a_id
        points_a += 3
    elif games_a_win < games_b_win:
        db_match.winner_id = db_match.player_b_id
        points_b += 3
    else:
        # Remíza (např. 1:1 na sety při dvouhraném formátu)
        db_match.winner_id = None
        points_a += 1
        points_b += 1

    db_match.is_finished = True

    # Uložení změn do databáze
    db.session.commit()
    # Tady triggerneš přepočet pro oba hráče
    stage = "Group" if db_match.group_id else "Playoff"
    if db_match.player_a_id:
        PlayerHelper.recalculate_player_stats(db_match.player_a_id, stage_name=stage)
    if db_match.player_b_id:
        PlayerHelper.recalculate_player_stats(db_match.player_b_id, stage_name=stage)
    return db_match.is_finished

def toggle_match_progress(match_id: int):
    """Přepne stav rozbalení/zavření zápasu na webu."""
    db_match = MatchModel.query.get_or_404(match_id)
    db_match.is_in_progress = not getattr(db_match, "is_in_progress", False)
    db.session.commit()