import sqlalchemy
from flask import render_template, request, redirect
from sqlalchemy import or_, func, cast, String
from sqlalchemy.orm import joinedload

from . import main_bp
from app.models.models import (
    db, Tournament as TournamentModel, Player as PlayerModel,
    GlobalPlayer as GlobalPlayerModel, Match as MatchModel,
    PlayoffStats as PlayoffStatsModel
)
from app.web.webmanager import WebManager
from datetime import datetime


def _render_tournament_stage(tournament_id, data_fetcher, template_name):
    """Pomocná funkce pro vyrenderování fáze turnaje v sekci statistik."""
    web_manager = WebManager(tournament_id)
    data = data_fetcher(web_manager)
    back_url, back_label = _get_back_navigation()

    # Používáme kwargs k předání specifických dat šabloně pod různými klíči
    # (šablony aktuálně očekávají 'group_data', 'p_data' nebo 'results')
    template_kwargs = {
        "tournament": web_manager.tournament,
        "editable": False,
        "prefix": f"/stats/tournament/{tournament_id}",
        "base_template": "stats/base_stats.html",
        "back_url": back_url,
        "back_label": back_label
    }

    # Přidání specifického klíče s daty podle toho, co template očekává
    if "groups" in template_name:
        template_kwargs["group_data"] = data
    elif "playoff" in template_name:
        template_kwargs["p_data"] = data
    elif "results" in template_name:
        template_kwargs["results"] = data

    return render_template(template_name, **template_kwargs)


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
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")

    # 1. Základní dotaz (připojení hráčů kvůli vítězi)
    query = TournamentModel.query.outerjoin(PlayerModel, TournamentModel.winner_id == PlayerModel.id)

    # 2. Filtrování v databázi (bez nutnosti stahovat vše přes .all() do paměti)
    if q:
        search_term = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(TournamentModel.name).like(search_term),
                func.lower(PlayerModel.name).like(search_term),
                cast(TournamentModel.total_players, String).like(search_term),
                cast(TournamentModel.date, String).like(search_term)
            )
        )

    # 3. Řazení v databázi
    sort_columns = {
        "name": TournamentModel.name,
        "winner": PlayerModel.name,
        "total_players": TournamentModel.total_players,
        "status": TournamentModel.is_finished,
        "date": TournamentModel.date
    }

    # Vybere správný sloupec, fallback na datum
    sort_col = sort_columns.get(sort_by, TournamentModel.date)

    # Aplikuje směr řazení
    if order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # Až nyní stáhneme (pouze vyfiltrovaná a seřazená) data z databáze
    tournaments = query.all()

    # 4. Vrácení výsledku pro HTMX partial nebo celou stránku
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
    return _render_tournament_stage(
        tournament_id,
        lambda wm: wm.get_groups_page_data(),
        "tournament/groups.html"
    )

@main_bp.route("/stats/tournament/<int:tournament_id>/playoff")
def stats_tournament_playoff(tournament_id):
    return _render_tournament_stage(
        tournament_id,
        lambda wm: wm.get_playoff_page_data(is_consolation=False),
        "tournament/playoff.html"
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/consolation_minigroup")
def stats_tournament_consolation_minigroup(tournament_id):
    return _render_tournament_stage(
        tournament_id,
        lambda wm: wm.get_minigroup_page_data(),
        "tournament/groups.html"
    )

@main_bp.route("/stats/tournament/<int:tournament_id>/consolation_playoff")
def stats_tournament_consolation_playoff(tournament_id):
    return _render_tournament_stage(
        tournament_id,
        lambda wm: wm.get_playoff_page_data(is_consolation=True),
        "tournament/consolation_playoff.html"
    )

@main_bp.route("/stats/tournament/<int:tournament_id>/results")
def stats_tournament_results(tournament_id):
    return _render_tournament_stage(
        tournament_id,
        lambda wm: wm.get_results_data(),
        "tournament/results.html"
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
    reverse_sort = (order == "desc")

    # 1. Získáme všechny hráče z databáze
    players = GlobalPlayerModel.query.all()

    # 2. Spolehlivý výpočet celkového pořadí (ranku) přes Python property 'total_points'
    all_players_sorted = sorted(players, key=lambda p: p.total_points or 0, reverse=True)
    ranks_map = {p.id: idx + 1 for idx, p in enumerate(all_players_sorted)}

    # 3. Filtrování v Pythonu podle vyhledávání
    if q:
        players = [p for p in players if q.lower() in (p.name or "").lower()]

    # 4. Řazení v Pythonu podle zvoleného kritéria
    if sort_by == "name":
        players.sort(key=lambda p: p.name or "", reverse=reverse_sort)
    else:
        players.sort(key=lambda p: p.total_points or 0, reverse=reverse_sort)

    # 5. Vrácení výsledku pro HTMX partial nebo celou stránku
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

    # 1. Základní dotaz s optimalizovaným načtením přes joinedload
    query = MatchModel.query.options(
        joinedload(MatchModel.player_a),
        joinedload(MatchModel.player_b),
        joinedload(MatchModel.tournament)
    ).join(TournamentModel, MatchModel.tournament_id == TournamentModel.id) \
     .filter(MatchModel.is_finished == True) \
     .filter(or_(MatchModel.player_a_id.isnot(None), MatchModel.player_b_id.isnot(None)))

    # Výchozí řazení v databázi (dle data turnaje a ID zápasu)
    query = query.order_by(TournamentModel.date.desc(), MatchModel.id.desc())
    matches = query.all()

    # 2. Bezpečné filtrování v Pythonu (zohledňuje i phase_display_name)
    if q:
        filtered_matches = []
        for m in matches:
            p_a_name = m.player_a.name.lower() if m.player_a and m.player_a.name else ""
            p_b_name = m.player_b.name.lower() if m.player_b and m.player_b.name else ""
            t_name = m.tournament.name.lower() if m.tournament and m.tournament.name else ""
            phase_name = m.phase_display_name.lower() if hasattr(m, 'phase_display_name') and m.phase_display_name else ""

            if q in p_a_name or q in p_b_name or q in t_name or q in phase_name:
                filtered_matches.append(m)
        matches = filtered_matches

    # 3. Řazení v Pythonu podle zvoleného sloupce
    if sort_by == "tournament":
        matches.sort(key=lambda x: (x.tournament.name if x.tournament else "", x.tournament.date if x.tournament else datetime.min.date()), reverse=reverse_sort)
    elif sort_by == "phase":
        matches.sort(key=lambda x: x.phase_display_name if hasattr(x, 'phase_display_name') and x.phase_display_name else "", reverse=reverse_sort)
    elif sort_by == "player_a":
        matches.sort(key=lambda x: x.player_a.name if x.player_a and x.player_a.name else "", reverse=reverse_sort)
    elif sort_by == "player_b":
        matches.sort(key=lambda x: x.player_b.name if x.player_b and x.player_b.name else "", reverse=reverse_sort)
    else:
        matches.sort(key=lambda x: (x.tournament.date if x.tournament else datetime.min.date(), x.id), reverse=reverse_sort)

    # 4. Vrácení výsledku (HTMX partial nebo celá stránka)
    if "HX-Request" in request.headers:
        return render_template(
            "stats/partials/_matches_table.html",
            matches=matches, q=q, sort_by=sort_by, order=order
        )

    return render_template(
        "stats/stats_matches.html",
        matches=matches, q=q, sort_by=sort_by, order=order
    )

@main_bp.route("/stats/player/<int:player_id>")
def stats_player_detail(player_id):
    from services.stats.player_stats import PlayerStatsService
    context = PlayerStatsService.get_player_profile_data(player_id, request.args)
    active_tab = context.get("active_tab", "overall")

    if request.headers.get("HX-Request"):
        template_map = {
            'overall': 'stats/partials/_tab_player_overall.html',
            'tournaments': 'stats/partials/_tab_player_tournaments.html',
            'matches': 'stats/partials/_tab_player_matches.html',
            'h2h': 'stats/partials/_tab_player_h2h.html',
        }
        return render_template(template_map.get(active_tab, 'stats/partials/_tab_player_overall.html'), **context)

    return render_template("stats/stats_player_detail.html", **context)