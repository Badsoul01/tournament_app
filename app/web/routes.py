from flask import Blueprint, render_template, request, redirect, session, send_file
from config import GROUPS_RULES, PLAYOFF_RULES
from app.services.setupwizard import SetupWizard
from app.models.models import db, Tournament as TournamentModel, Player as PlayerModel, GlobalPlayer as GlobalPLayerModel,\
    ConsolationStats as ConsolationStatsModel, PlayoffStats as PlayoffStatsModel,GroupStats as GroupsStatsModel
from app.services.tournament import Tournament as TournamentOrchestrator
from app.services.match import evaluate, toggle_match_progress, unlock_match
from app.web.webmanager import WebManager
from app.services.queries import get_available_players_from_tournament, get_recent_finished_tournaments

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
    all_global_players = [g.name for g in GlobalPLayerModel.query.order_by(GlobalPLayerModel.name.asc()).all()]

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