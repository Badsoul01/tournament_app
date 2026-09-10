from flask import Blueprint, render_template, request, redirect, session, send_file
from config import GROUPS_RULES, PLAYOFF_RULES
from app.services.setupwizard import SetupWizard
from app.models.models import Tournament as TournamentModel, Player as PlayerModel, GlobalPlayer as GlobalPlayerModel,\
    ConsolationStats as ConsolationStatsModel, PlayoffStats as PlayoffStatsModel, Match as MatchModel
from app.services.tournament import Tournament as TournamentOrchestrator
from app.services.match import evaluate, toggle_match_progress, unlock_match
from app.web.webmanager import WebManager
from app.services.queries import get_available_players_from_tournament, get_recent_finished_tournaments
from sqlalchemy import or_
from sqlalchemy.orm import aliased




main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("index.html")


@main_bp.route("/settings_groups", methods=["GET", "POST"])
def settings_groups():
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    if request.method == "POST":
        action = request.form.get("action")
        print(f"DEBUG: Přišla akce: {action}")
        print(f"DEBUG: Form data: {request.form}")

        wizard.process_form_action(form_data=request.form)

        if action == "cancel":
            session.pop("wizard_data", None)
            return redirect("/")

        if action == "next":
            session["wizard_data"] = wizard.import_to_dict()
            return redirect("/settings_playoff")

        session["wizard_data"] = wizard.import_to_dict()

        # Pokud požadavek přišel přes HTMX:
        if "HX-Request" in request.headers:
            active_tournament_id = request.form.get("active_tournament_id")

            # 1. Vyrenderujeme hlavní část wizardu
            main_html = render_template(
                "partials/_wizard_content.html",
                wizard=wizard,
                GROUPS_RULES=GROUPS_RULES
            )

            # 2. Pokud byl vybraný nějaký turnaj, přibalíme aktualizované okénko hráčů (OOB swap)
            if active_tournament_id and active_tournament_id.isdigit():
                t_id = int(active_tournament_id)
                available_players = get_available_players_from_tournament(t_id, wizard)
                selected_tournament = TournamentModel.query.get(t_id)

                oob_html = f'<div id="past-players-container" hx-swap-oob="true">' \
                           f'{render_template("partials/_past_tournament_players.html", available_players=available_players, selected_tournament=selected_tournament)}' \
                           f'</div>'

                return main_html + oob_html

            return main_html

    recent_tournaments = get_recent_finished_tournaments(limit=5)

    # načteme všechna jména z GlobalPlayer pro našeptávač
    all_global_players = [g.name for g in GlobalPlayerModel.query.order_by(GlobalPlayerModel.name.asc()).all()]

    return render_template(
        "settings_groups.html",
        wizard=wizard,
        GROUPS_RULES=GROUPS_RULES,
        recent_tournaments=recent_tournaments
    )

@main_bp.route("/wizard/search-tournaments")
def search_tournaments():
    query = request.args.get("q", "").strip()

    if not query:
        tournaments = get_recent_finished_tournaments(limit=5)
    else:
        tournaments = TournamentModel.query.filter(
            TournamentModel.is_finished == True,
            TournamentModel.name.ilike(f"%{query}%")
        ).order_by(TournamentModel.date.desc()).limit(10).all()

    return render_template("partials/_past_tournaments_list.html", recent_tournaments=tournaments)

@main_bp.route("/wizard/past-tournament/<int:tournament_id>/players")
def get_past_tournament_players(tournament_id):
    """
    Routa určená pro HTMX request při kliknutí na minulý turnaj.
    Vrátí HTML partial se seznamem hráčů.
    """
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    available_players = get_available_players_from_tournament(tournament_id, wizard)
    selected_tournament = TournamentModel.query.get(tournament_id)

    return render_template(
        "partials/_past_tournament_players.html",
        available_players=available_players,
        selected_tournament=selected_tournament
    )

@main_bp.route("/settings_playoff", methods=["GET", "POST"])
def settings_playoff():
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    if request.method == "POST":
        action = request.form.get("action")
        print(f"DEBUG: Přišla akce: {action}")
        print(f"DEBUG: Form data: {request.form}")

        if action == "next":
            wizard.playoff_match_format = int(request.form.get("playoff_match_format"))
            wizard.playoff_elimination_action = request.form.get("elimination_actions")

            session["wizard_data"] = wizard.import_to_dict()

            if not wizard.check_readiness():
                return render_template(
                    "settings_playoff.html",
                    wizard=wizard,
                    PLAYOFF_RULES=PLAYOFF_RULES,
                    error="Turnaj není připraven"
                )

            # ================
            # DATABÁZE A PAMĚŤ
            # ================
            new_tournament = TournamentOrchestrator(wizard)

            session.pop("wizard_data", None)

            return redirect(f"/tournament/{new_tournament.id}/groups")

    return render_template(
        "settings_playoff.html",
        wizard=wizard,
        PLAYOFF_RULES=PLAYOFF_RULES
    )

@main_bp.route("/stats")
def stats_index():
    return redirect("/stats/tournaments")

@main_bp.route("/stats/tournaments")
def stats_tournament_view():
    # Načtení parametrů z URL (pokud nejsou, nastavíme výchozí hodnoty)
    q = request.args.get("q","").strip()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")

    # Základní dotaz - použiujeme outerjoin na PlayerModel, abychom mohli řadit podle vítěze
    query = TournamentModel.query.outerjoin(PlayerModel, TournamentModel.winner_id == PlayerModel.id)

    # 1. Vyhledávání (vyhledáváme v názvu turnaje)
    if q:
        query = query.filter(TournamentModel.name.ilike(f"%{q}%"))

    # 2. Řazení
    if sort_by == "name":
        sort_column = TournamentModel.name
    elif sort_by == "winner":
        # Zde řadíme podle jména propojeného hráče (vítěze)
        sort_column = PlayerModel.name
    elif sort_by == "total_players":
        sort_column = TournamentModel.total_players
    else:
        # Výchozí řazení
        sort_column = TournamentModel.date

    # Aplikujeme směr řazení
    if order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Spuštění dotazu a načtení výsledků
    tournaments = query.all()

    return render_template(
        "stats_tournaments.html",
        tournaments=tournaments,
        q=q,
        sort_by=sort_by,
        order=order
    )

@main_bp.route("/stats/players")
def stats_players_view():
    # Načtení parametrů z URL
    q = request.args.get("q","").strip()
    sort_by = request.args.get("sort_by", "total_points")
    order = request.args.get("order","desc")

    # Základní dotaz
    query = GlobalPlayerModel.query

    # Vyhledávání (podle jména)
    if q:
        query = query.filter(GlobalPlayerModel.name.ilike(f"%{q}%"))

    # Řazení
    if sort_by == "name":
        sort_column = GlobalPlayerModel.name
    elif sort_by == "last_points":
        sort_column = GlobalPlayerModel.last_points_gained
    elif sort_by == "matches_played":
        sort_column = GlobalPlayerModel.matches_played
    elif sort_by == "won":
        sort_column = GlobalPlayerModel.matches_won
    elif sort_by == "lost":
        sort_column = GlobalPlayerModel.matches_lost
    elif sort_by == "drawn":
        sort_column = GlobalPlayerModel.matches_drawn
    elif sort_by == "tournaments":
        sort_column = GlobalPlayerModel.tournaments_played
    elif sort_by == "last_date":
        sort_column = GlobalPlayerModel.last_tournament_date
    else:
        # Výchozí řazení
        sort_column = GlobalPlayerModel.total_points

    # Aplikujeme směr řazení
    if order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    players = query.all()

    return render_template(
        "stats_players.html",
        players=players,
        q=q,
        sort_by=sort_by,
        order=order
    )


@main_bp.route("/stats/matches")
def stats_matches_view():
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")

    PlayerA = aliased(PlayerModel)
    PlayerB = aliased(PlayerModel)
    GlobalA = aliased(GlobalPlayerModel)
    GlobalB = aliased(GlobalPlayerModel)

    # Chceme jen dokončené zápasy
    query = MatchModel.query.join(TournamentModel, MatchModel.tournament_id == TournamentModel.id) \
        .filter(MatchModel.is_finished == True)

    # Filtrujeme pryč zápasy, kde jsou oba hráči prázdní (BYE vs BYE / Neznámý vs Neznámý) ---
    query = query.filter(
        or_(MatchModel.player_a_id.isnot(None), MatchModel.player_b_id.isnot(None))
    )

    # Připojíme hráče A a B
    query = query.outerjoin(PlayerA, MatchModel.player_a_id == PlayerA.id) \
        .outerjoin(GlobalA, PlayerA.global_player_id == GlobalA.id) \
        .outerjoin(PlayerB, MatchModel.player_b_id == PlayerB.id) \
        .outerjoin(GlobalB, PlayerB.global_player_id == GlobalB.id)

    # Filtrování (vyhledávání)
    if q:
        query = query.filter(or_(
            GlobalA.name.ilike(f"%{q}%"),
            GlobalB.name.ilike(f"%{q}%"),
            TournamentModel.name.ilike(f"%{q}%")
        ))

    # Logika pro řazení
    if sort_by == "tournament":
        sort_column = TournamentModel.name
    elif sort_by == "phase":
        sort_column = MatchModel.match_type
    elif sort_by == "player_a":
        sort_column = PlayerA.name
    elif sort_by == "player_b":
        sort_column = PlayerB.name
    else:
        # Výchozí řazení (pokud nic nevybereme, nebo vybereme "date")
        sort_column = TournamentModel.date

    # Aplikování směru řazení (jako druhé pravidlo vždy přidáváme MatchModel.id, aby se zápasy ze stejného turnaje nemíchaly)
    if sort_by == "date":
        query = query.order_by(TournamentModel.date.desc(), MatchModel.id.desc())
    else:
        if order == "asc":
            query = query.order_by(sort_column.asc(), MatchModel.id.asc())
        else:
            query = query.order_by(sort_column.desc(), MatchModel.id.desc())

    matches = query.all()

    return render_template(
        "stats_matches.html",
        matches=matches,
        q=q,
        sort_by=sort_by,
        order=order
    )

@main_bp.route("/stats/match/<int:match_id>")
def stats_match_detail_view(match_id):
    match = MatchModel.query.get_or_404(match_id)
    return f"Zde se zobrazí detail Zápasu ID: {match.id}"

@main_bp.route("/stats/player/<int:player_id>")
def stats_player_detail(player_id):
    # Najdeme hráče podle ID, pokud neexistuje, vrátí 404
    player = GlobalPlayerModel.query.get_or_404(player_id)

    return render_template("stats_player_detail.html", player=player)


@main_bp.route("/tournament/<int:tournament_id>/groups", methods=["GET", "POST"])
def groups_view(tournament_id):
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        # Získáme navíc informaci, v jaké skupině se akce stala
        group_name = request.form.get("group_name")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.group_manager.handle_match_completion(match_id, web_manager.tournament)

        # --- ZMĚNA PRO HTMX ---
        if "HX-Request" in request.headers:
            # Načteme čerstvá data turnaje
            group_data = web_manager.get_groups_page_data()

            # Vrátíme pouze HTML fragment (tzv. partial) dané skupiny
            return render_template(
                "partials/_group_content.html",
                group_name=group_name,
                data=group_data[group_name],
                tournament=web_manager.tournament
            )

        return redirect(f"/tournament/{tournament_id}/groups")

    group_data = web_manager.get_groups_page_data()
    return render_template("groups.html", tournament=web_manager.tournament, group_data=group_data)


@main_bp.route("/tournament/<int:tournament_id>/playoff", methods=["GET", "POST"])
def playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.handle_playoff_completion(is_consolation=False)

        # --- ZMĚNA PRO HTMX ---
        if "HX-Request" in request.headers:
            # Načteme aktualizovaná data pavouka
            p_data = web_manager.get_playoff_page_data(is_consolation=False)

            return render_template(
                "partials/_playoff_content.html",
                tournament=web_manager.tournament,
                p_data=p_data
            )

        return redirect(f"/tournament/{tournament_id}/playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=False)
    return render_template("playoff.html", tournament=web_manager.tournament, p_data=p_data)


@main_bp.route("/tournament/<int:tournament_id>/consolation_minigroup", methods=["GET", "POST"])
def consolation_minigroup_view(tournament_id):
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")
        group_name = request.form.get("group_name")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.group_manager.handle_match_completion(match_id, web_manager.tournament)

        if "HX-Request" in request.headers:
            group_data = web_manager.get_minigroup_page_data()
            return render_template(
                "partials/_group_content.html",
                group_name=group_name,
                data=group_data[group_name],
                tournament=web_manager.tournament,
                is_consolation=True
            )

        return redirect(f"/tournament/{tournament_id}/consolation_minigroup")

    group_data = web_manager.get_minigroup_page_data()
    return render_template("consolation_minigroup.html", tournament=web_manager.tournament, group_data=group_data, is_consolation=True)


@main_bp.route("/tournament/<int:tournament_id>/consolation_playoff", methods=["POST", "GET"])
def consolation_playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.handle_playoff_completion(is_consolation=True)

        if "HX-Request" in request.headers:
            p_data = web_manager.get_playoff_page_data(is_consolation=True)
            return render_template(
                "partials/_playoff_content.html",
                tournament=web_manager.tournament,
                p_data=p_data
            )

        return redirect(f"/tournament/{tournament_id}/consolation_playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=True)
    return render_template("consolation_playoff.html", tournament=web_manager.tournament, p_data=p_data)


@main_bp.route("/tournament/<int:tournament_id>/results", methods=["GET", "POST"])
def results_view(tournament_id):
    current_tournament = TournamentModel.query.get_or_404(tournament_id)
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "download":
            file_stream = web_manager.generate_results_excel()

            safe_tournament_name = "".join(
                c for c in web_manager.tournament.name if c.isalnum() or c in (' ', '_', '-')
            ).strip().replace(' ', '_')
            filename = f"vysledky_{safe_tournament_name}.xlsx"

            return send_file(
                file_stream,
                as_attachment=True,
                download_name=filename,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        elif action == "finish_tournament":
            TournamentOrchestrator.finish_existing_tournament(tournament_id)
            return redirect(f"/tournament/{tournament_id}/results")

    # Načtení výsledků pro zobrazení v tabulce z nových tabulek PlayoffStats a ConsolationStats
    players = PlayerModel.query.filter_by(tournament_id=tournament_id).all()
    results_data = []

    for player in players:
        p_stats = PlayoffStatsModel.query.filter_by(player_id=player.id).first()
        c_stats = ConsolationStatsModel.query.filter_by(player_id=player.id).first()

        rank = None
        if p_stats and p_stats.final_rank is not None:
            rank = p_stats.final_rank
        elif c_stats and c_stats.final_rank is not None:
            rank = c_stats.final_rank

        if rank is not None:
            results_data.append((player, rank))

    # Seřadíme podle získaného pořadí vzestupně (1., 2., 3. místo...)
    results_data.sort(key=lambda x: x[1])

    return render_template("results.html", tournament=current_tournament, results=results_data)


@main_bp.route("/reset_settings", methods=["POST"])
def reset_settings():
    session.pop("wizard_data", None)
    return redirect("/settings_groups")