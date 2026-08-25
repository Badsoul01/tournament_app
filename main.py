import os
from flask import Flask, render_template, request, redirect, session
from dotenv import load_dotenv
from flask_migrate import Migrate
from config import TOURNAMENT_RULES, GROUPS_RULES, PLAYOFF_RULES
from setupwizard import SetupWizard
from models import db, Tournament as TournamentModel, Player as PlayerModel, PlayerStats as PlayerStatsModel
from tournament import Tournament as TournamentOrchestrator
from match import evaluate,toggle_match_progress
from webmanager import WebManager


load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "zalozni_tajny_kod")
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    db_url = "postgresql://postgres:Cdd9VbGzVfzeZ2AV@db.vlgumdlyjuefpwmjubru.supabase.co:6543/postgres"
print(bytes(f"DEBUG DATABASE URL: {db_url}", "utf-8")) # vytiskne se to do logů Renderu
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app,db)


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/settings_basic", methods=["GET","POST"])
def settings_basic():
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    if request.method== "POST":
        action = request.form.get("action")
        print(f"DEBUG: Přišla akce: {action}")
        print(f"DEBUG:Form data: {request.form}")

        wizard.selected_format = request.form.get("available_formats")
        if action == "cancel":
            session.pop("wizard_data", None)
            return redirect("/")


        wizard.import_from_dict(request.form.to_dict())
        session["wizard_data"] = wizard.import_to_dict()
        return redirect("/settings_groups")

    return render_template("settings_basic.html",
                           wizard=wizard,
                           all_formats = TOURNAMENT_RULES["available_formats"])

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
        session["wizard_data"] = wizard.import_to_dict()

        if action == "next":
            return redirect("/settings_playoff")

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

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.group_manager.handle_match_completion(match_id, web_manager.tournament)

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
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.handle_playoff_completion(is_consolation=False)

        return redirect(f"/tournament/{tournament_id}/playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=False)
    return render_template("playoff.html", tournament=web_manager.tournament, p_data=p_data)


@app.route("/tournament/<int:tournament_id>/consolation_minigroup", methods=["GET", "POST"])
def consolation_minigroup_view(tournament_id):
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.group_manager.handle_match_completion(match_id, web_manager.tournament)

        return redirect(f"/tournament/{tournament_id}/consolation_minigroup")

    group_data = web_manager.get_minigroup_page_data()
    return render_template("consolation_minigroup.html", tournament=web_manager.tournament, group_data=group_data)


@app.route("/tournament/<int:tournament_id>/consolation_playoff", methods=["POST", "GET"])
def consolation_playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.handle_playoff_completion(is_consolation=True)

        return redirect(f"/tournament/{tournament_id}/consolation_playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=True)
    return render_template("consolation_playoff.html", tournament=web_manager.tournament, p_data=p_data)

@app.route("/tournament/<int:tournament_id>/results", methods=["GET"])
def results_view(tournament_id):
        current_tournament = TournamentModel.query.get_or_404(tournament_id)

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
    return redirect("/settings_basic")

if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0")