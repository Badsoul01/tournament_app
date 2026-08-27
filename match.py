from models import db, Match as MatchModel, MatchResults as MatchResultsModel
from player import PlayerHelper


def evaluate(match_id, player_a_games: list, player_b_games: list) -> bool:
    """
    Vyhodnotí zápas na základě odehraných setů:
    1. Zpracuje sety z webu a uloží je do samostatné tabulky MatchSet.
    2. Spočítá celkové skóre setů z těchto setů.
    3. Určí vítěze, nebo ošetří remízu (winner_id = None).
    4. Uloží stav do databáze a přepočítá statistiky.
    """
    if not player_a_games or not player_b_games:
        return False

    played_games = []
    for a, b in zip(player_a_games, player_b_games):
        if a != "" and b != "":
            played_games.append((int(a), int(b)))

    db_match = MatchModel.query.get_or_404(match_id)

    # Nejprve smažeme staré sety, kdyby se zápas přepisoval / přehrával znovu
    MatchResultsModel.query.filter_by(match_id=db_match.id).delete()

    games_a_win = 0
    games_b_win = 0

    # Projdeme jednotlivé sety z formuláře a uložíme je do nové tabulky
    for index, (balls_a, balls_b) in enumerate(played_games, start=1):
        if balls_a > balls_b:
            games_a_win += 1
        elif balls_b > balls_a:
            games_b_win += 1

        # Vytvoříme nový řádek v tabulce match_sets
        new_set = MatchResultsModel(
            match_id=db_match.id,
            set_number=index,
            score_a=balls_a,
            score_b=balls_b
        )
        db.session.add(new_set)

    # Uložíme celkové skóre setů do modelu zápasu (pokud si score_a/score_b v Matchnech chceš nechat)
    db_match.score_a = games_a_win
    db_match.score_b = games_b_win

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
        # Remíza
        db_match.winner_id = None
        points_a += 1
        points_b += 1

    db_match.is_finished = True

    # Uložení změn do databáze
    db.session.commit()

    # Přepočet statistik pro oba hráče
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