from flask import Blueprint, render_template, request, redirect, session, send_file
from config import GROUPS_RULES, PLAYOFF_RULES
from app.services.setupwizard import SetupWizard
from app.models.models import db, Tournament as TournamentModel, Player as PlayerModel, PlayerStats as PlayerStatsModel
from app.services.tournament import Tournament as TournamentOrchestrator
from app.services.match import evaluate, toggle_match_progress, unlock_match
from app.web.webmanager import WebManager

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

    return render_template(
        "settings_groups.html",
        wizard=wizard,
        GROUPS_RULES=GROUPS_RULES
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

    results_data = db.session.query(PlayerModel, PlayerStatsModel.final_rank) \
        .join(PlayerStatsModel, PlayerModel.id == PlayerStatsModel.player_id) \
        .filter(PlayerModel.tournament_id == tournament_id) \
        .filter(PlayerStatsModel.final_rank.isnot(None)) \
        .order_by(PlayerStatsModel.final_rank.asc()) \
        .all()

    return render_template("results.html", tournament=current_tournament, results=results_data)


@main_bp.route("/reset_settings", methods=["POST"])
def reset_settings():
    session.pop("wizard_data", None)
    return redirect("/settings_groups")