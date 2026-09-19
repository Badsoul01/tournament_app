from flask import render_template, request, redirect
from sqlalchemy import or_

from . import main_bp
from app.models.models import (
    db, Tournament as TournamentModel, Player as PlayerModel,
    GlobalPlayer as GlobalPlayerModel, Match as MatchModel,
    PlayoffStats as PlayoffStatsModel
)
from app.web.webmanager import WebManager
from app.services.stats.match_stats import MatchStatsService
from datetime import datetime


def _get_back_navigation():
    """Pomocná funkce pro unifikované určení, kam směřuje tlačítko 'Zpět'."""
    from_source = request.args.get("from")
    player_id = request.args.get("player_id")

    if from_source == "player" and player_id:
        return f"/stats/player/{player_id}", "← Zpět na hráče"
    return "/stats/tournaments", "← Seznam turnajů"


@main_bp.route("/stats")
def stats_index():
    return redirect("/stats/tournaments")


@main_bp.route("/stats/tournaments")
def stats_tournament_view():
    q = request.args.get("q", "").strip().lower()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")
    reverse_sort = (order == "desc")

    # 1. Získáme všechna data z databáze
    query = TournamentModel.query.outerjoin(PlayerModel, TournamentModel.winner_id == PlayerModel.id)
    tournaments = query.all()

    # 2. Filtrování v Pythonu
    if q:
        filtered_tournaments = []
        for t in tournaments:
            t_name = t.name.lower() if t.name else ""
            winner_name = t.winner.name.lower() if t.winner and t.winner.name else ""
            players_str = str(t.total_players) if t.total_players is not None else ""

            # Převedeme datum na textové formáty pro snadné vyhledávání
            date_str = ""
            if t.date:
                d_dot = t.date.strftime('%d.%m.%Y').lower() if hasattr(t.date, 'strftime') else str(t.date)
                d_iso = t.date.strftime('%Y-%m-%d').lower() if hasattr(t.date, 'strftime') else ""
                date_str = f"{d_dot} {d_iso}"

            if q in t_name or q in winner_name or q in date_str or q in players_str:
                filtered_tournaments.append(t)
        tournaments = filtered_tournaments

    # 3. Spolehlivé řazení v Pythonu
    if sort_by == "name":
        tournaments.sort(key=lambda x: x.name or "", reverse=reverse_sort)
    elif sort_by == "winner":
        tournaments.sort(key=lambda x: x.winner.name if x.winner else "", reverse=reverse_sort)
    elif sort_by == "total_players":
        tournaments.sort(key=lambda x: x.total_players or 0, reverse=reverse_sort)
    elif sort_by == "status":
        tournaments.sort(key=lambda x: x.is_finished, reverse=reverse_sort)
    else:
        tournaments.sort(key=lambda x: x.date or datetime.min.date(), reverse=reverse_sort)

    # 4. Vrácení výsledku (HTMX partial nebo celá stránka)
    if "HX-Request" in request.headers:
        return render_template(
            "stats/partials/_tournaments_table.html",
            tournaments=tournaments, q=q, sort_by=sort_by, order=order
        )

    return render_template(
        "stats/stats_tournaments.html",
        tournaments=tournaments, q=q, sort_by=sort_by, order=order
    )


@main_bp.route("/stats/tournament/<int:tournament_id>")
def stats_tournament_redirect(tournament_id):
    return redirect(f"/stats/tournament/{tournament_id}/groups")


@main_bp.route("/stats/tournament/<int:tournament_id>/groups")
def stats_tournament_groups(tournament_id):
    web_manager = WebManager(tournament_id)
    group_data = web_manager.get_groups_page_data()
    back_url, back_label = _get_back_navigation()

    return render_template(
        "tournament/groups.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        editable=False,
        prefix=f"/stats/tournament/{tournament_id}",
        base_template="stats/base_stats.html",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/playoff")
def stats_tournament_playoff(tournament_id):
    web_manager = WebManager(tournament_id)
    p_data = web_manager.get_playoff_page_data(is_consolation=False)
    back_url, back_label = _get_back_navigation()

    return render_template(
        "tournament/playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=False,
        base_template="stats/base_stats.html",
        prefix=f"/stats/tournament/{tournament_id}",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/consolation_minigroup")
def stats_tournament_consolation_minigroup(tournament_id):
    web_manager = WebManager(tournament_id)
    group_data = web_manager.get_minigroup_page_data()
    back_url, back_label = _get_back_navigation()

    return render_template(
        "tournament/groups.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        editable=False,
        prefix=f"/stats/tournament/{tournament_id}",
        base_template="stats/base_stats.html",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/consolation_playoff")
def stats_tournament_consolation_playoff(tournament_id):
    web_manager = WebManager(tournament_id)
    p_data = web_manager.get_playoff_page_data(is_consolation=True)
    back_url, back_label = _get_back_navigation()

    return render_template(
        "tournament/consolation_playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=False,
        base_template="stats/base_stats.html",
        prefix=f"/stats/tournament/{tournament_id}",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/results")
def stats_tournament_results(tournament_id):
    web_manager = WebManager(tournament_id)
    results_data = web_manager.get_results_data()
    back_url, back_label = _get_back_navigation()

    return render_template(
        "tournament/results.html",
        tournament=web_manager.tournament,
        results=results_data,
        prefix=f"/stats/tournament/{tournament_id}",
        base_template="stats/base_stats.html",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/details")
def stats_tournament_details(tournament_id):
    tournament = TournamentModel.query.get_or_404(tournament_id)

    top_players = db.session.query(PlayerModel, PlayoffStatsModel.final_rank)\
        .join(PlayoffStatsModel, PlayerModel.id == PlayoffStatsModel.player_id)\
        .filter(PlayerModel.tournament_id == tournament_id, PlayoffStatsModel.final_rank <= 3)\
        .order_by(PlayoffStatsModel.final_rank.asc())\
        .all()

    top_3 = {rank: {"name": player.name, "global_id": player.global_player_id} for player, rank in top_players}

    return render_template("stats/partials/_tournament_details_row.html", tournament=tournament, top_3=top_3)


@main_bp.route("/stats/players")
def stats_players_view():
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "total_points")
    order = request.args.get("order", "desc")

    players = GlobalPlayerModel.query.all()
    if q:
        players = [p for p in players if q.lower() in p.name.lower()]

    all_players_sorted = GlobalPlayerModel.query.all()
    all_players_sorted.sort(key=lambda p: p.total_points, reverse=True)
    ranks_map = {p.id: idx + 1 for idx, p in enumerate(all_players_sorted)}

    reverse_sort = (order == "desc")
    if sort_by == "name":
        players.sort(key=lambda p: p.name, reverse=reverse_sort)
    else:
        players.sort(key=lambda p: p.total_points, reverse=reverse_sort)

    if "HX-Request" in request.headers:
        return render_template(
            "stats/partials/_players_table.html",
            players=players, ranks_map=ranks_map, q=q, sort_by=sort_by, order=order
        )

    return render_template(
        "stats/stats_players.html",
        players=players, ranks_map=ranks_map, q=q, sort_by=sort_by, order=order
    )


@main_bp.route("/stats/matches")
def stats_matches_view():
    q = request.args.get("q", "").strip().lower()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")
    reverse_sort = (order == "desc")

    query = MatchModel.query.join(TournamentModel, MatchModel.tournament_id == TournamentModel.id) \
        .filter(MatchModel.is_finished == True) \
        .filter(or_(MatchModel.player_a_id.isnot(None), MatchModel.player_b_id.isnot(None)))

    query = query.order_by(TournamentModel.date.desc(), MatchModel.id.desc())
    matches = query.all()

    if q:
        filtered_matches = []
        for m in matches:
            p_a_name = m.player_a.name.lower() if m.player_a else ""
            p_b_name = m.player_b.name.lower() if m.player_b else ""
            t_name = m.tournament.name.lower() if m.tournament else ""
            phase_name = m.phase_display_name.lower() if hasattr(m, 'phase_display_name') else ""

            if q in p_a_name or q in p_b_name or q in t_name or q in phase_name:
                filtered_matches.append(m)
        matches = filtered_matches

    if sort_by == "tournament":
        matches.sort(key=lambda x: (x.tournament.name if x.tournament else "", x.tournament.date if x.tournament else datetime.min.date()), reverse=reverse_sort)
    elif sort_by == "phase":
        matches.sort(key=lambda x: x.phase_display_name if hasattr(x, 'phase_display_name') else "", reverse=reverse_sort)
    elif sort_by == "player_a":
        matches.sort(key=lambda x: x.player_a.name if x.player_a else "", reverse=reverse_sort)
    elif sort_by == "player_b":
        matches.sort(key=lambda x: x.player_b.name if x.player_b else "", reverse=reverse_sort)
    else:
        matches.sort(key=lambda x: (x.tournament.date if x.tournament else datetime.min.date(), x.id), reverse=reverse_sort)

    if "HX-Request" in request.headers:
        return render_template(
            "stats/partials/_matches_table.html",
            matches=matches, q=q, sort_by=sort_by, order=order
        )

    return render_template(
        "stats/stats_matches.html",
        matches=matches, q=q, sort_by=sort_by, order=order
    )


@main_bp.route("/stats/match/<int:match_id>")
def stats_match_detail_view(match_id):
    context = MatchStatsService.get_match_detail_context(match_id)
    return render_template("stats/partials/_match_details_row.html", **context)


@main_bp.route("/stats/player/<int:player_id>")
def stats_player_detail(player_id):
    from services.stats.stats_player_detail import PlayerStatsService
    context = PlayerStatsService.get_player_profile_data(player_id, request.args)
    active_tab = context.get("active_tab", "obecne")

    if request.headers.get("HX-Request"):
        template_map = {
            'obecne': 'stats/partials/_tab_player_overall.html',
            'turnaje': 'stats/partials/_tab_player_tournaments.html',
            'zapasy': 'stats/partials/_tab_player_matches.html',
            'h2h': 'stats/partials/_tab_player_h2h.html',
        }
        return render_template(template_map.get(active_tab, 'stats/partials/_tab_player_overall.html'), **context)

    return render_template("stats/stats_player_detail.html", **context)