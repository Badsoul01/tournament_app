import os
from flask import Flask, render_template, request, redirect, session, send_file
from dotenv import load_dotenv
from flask_migrate import Migrate
from config import GROUPS_RULES, PLAYOFF_RULES
from setupwizard import SetupWizard
from models import db, Tournament as TournamentModel, Player as PlayerModel, PlayerStats as PlayerStatsModel
from tournament import Tournament as TournamentOrchestrator
from match import evaluate,toggle_match_progress, unlock_match
from webmanager import WebManager


load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "zalozni_tajny_kod")
db_url = os.environ.get("DATABASE_URL")


print(bytes(f"DEBUG DATABASE URL: {db_url}", "utf-8")) # vytiskne se to do logů Renderu
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app,db)


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/settings_groups", methods=["GET","POST"])
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

    return render_template("settings_groups.html",
                           wizard=wizard,
                           GROUPS_RULES = GROUPS_RULES)

@app.route("/settings_playoff",methods=["GET","POST"])
def settings_playoff():
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    if request.method == "POST":
        action = request.form.get("action")
        print(f"DEBUG: Přišla akce: {action}")
        print(f"DEBUG:Form data: {request.form}")

        if action == "next":

            wizard.playoff_match_format = int(request.form.get("playoff_match_format"))
            wizard.playoff_elimination_action = request.form.get("elimination_actions")

            session["wizard_data"] = wizard.import_to_dict()

            if not wizard.check_readiness():
                return render_template("settings_playoff.html",
                                       wizard=wizard,
                                       PLAYOFF_RULES=PLAYOFF_RULES,
                                       error="Turnaj není připraven")


            # ================
            # DATABÁZE A PAMĚŤ
            # ================

            new_tournament = TournamentOrchestrator(wizard)

            session.pop("wizard_data", None)

            return redirect(f"/tournament/{new_tournament.id}/groups")



    return render_template("settings_playoff.html",
                           wizard=wizard,
                           PLAYOFF_RULES=PLAYOFF_RULES)


@app.route("/tournament/<int:tournament_id>/groups", methods=["GET", "POST"])
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
            # Nemusíme posílat celou stránku, ušetříme výkon a zrychlíme odezvu
            return render_template(
                "partials/_group_content.html",
                group_name=group_name,
                data=group_data[group_name],
                tournament=web_manager.tournament
            )


        return redirect(f"/tournament/{tournament_id}/groups")

    group_data = web_manager.get_groups_page_data()
    return render_template("groups.html", tournament=web_manager.tournament, group_data=group_data)


@app.route("/tournament/<int:tournament_id>/playoff", methods=["GET", "POST"])
def playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        if action == "toggle_progress":
            toggle_match_progress(match_id)

        if action == "edit_match":
            unlock_match(match_id=match_id)

        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.handle_playoff_completion(is_consolation=False)

        # --- ZMĚNA PRO HTMX ---
        if "HX-Request" in request.headers:
            # Načteme aktualizovaná data pavouka po našem zásahu do databáze
            p_data = web_manager.get_playoff_page_data(is_consolation=False)

            # Vrátíme pouze HTML fragment.
            # Opět potřebujeme vytvořit soubor "_playoff_content.html" ve složce partials
            return render_template(
                "partials/_playoff_content.html",
                tournament=web_manager.tournament,
                p_data=p_data
            )


        return redirect(f"/tournament/{tournament_id}/playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=False)
    return render_template("playoff.html", tournament=web_manager.tournament, p_data=p_data)


@app.route("/tournament/<int:tournament_id>/consolation_minigroup", methods=["GET", "POST"])
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


@app.route("/tournament/<int:tournament_id>/consolation_playoff", methods=["POST", "GET"])
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


@app.route("/tournament/<int:tournament_id>/results", methods=["GET", "POST"])
def results_view(tournament_id):
    current_tournament = TournamentModel.query.get_or_404(tournament_id)
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "download":
            file_stream = web_manager.generate_results_excel()

            safe_tournament_name = "".join(
                c for c in web_manager.tournament.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
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

@app.route("/reset_settings", methods=["POST"])
def reset_settings():
    session.pop("wizard_data", None)
    return redirect("/settings_groups")

if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0")