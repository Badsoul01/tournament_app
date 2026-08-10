from flask import Flask,render_template,request,redirect,session
from webmanager import WebManager
from config import TOURNAMENT_RULES, GROUPS_RULES, PLAYOFF_RULES, STATE_OF_WIZARD
from setupwizard import SetupWizard
from tournament import Tournament

app = Flask(__name__)
app.secret_key = "Ultra tajny kod"
active_tournament = None
web_manager = None


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

        session["wizard_data"] = wizard.import_to_dict()
        if action == "back":
            return redirect("/settings_groups")


        if action == "next":
            if not wizard.check_readiness():
                return render_template("settings_playoff.html",
                                       wizard=wizard,
                                       PLAYOFF_RULES=PLAYOFF_RULES,
                                       error="Turnaj není připraven")

            wizard.playoff_match_format = int(request.form.get("playoff_match_format"))
            wizard.playoff_elimination_action = request.form.get("elimination_actions")
            global active_tournament
            global web_manager
            active_tournament = Tournament(wizard)
            web_manager = WebManager(active_tournament)
            return redirect("/groups")



    return render_template("settings_playoff.html",
                           wizard=wizard,
                           PLAYOFF_RULES=PLAYOFF_RULES)

@app.route("/groups", methods=["GET", "POST"])
def update_match():
    if active_tournament is None:
        return redirect("/")

    if request.method == "POST":
        web_manager.process_match_action(
           match_id= int(request.form.get("match_id")),
           action=request.form.get("action"),
           games_a=request.form.getlist("game_a[]"),
           games_b=request.form.getlist("game_b[]")
        )

        return redirect("/groups")


    return render_template("groups.html",
                           tournament=active_tournament,
                           web_manager=web_manager,
                           group_data = web_manager.get_groups_for_web("main"))

@app.route("/playoff", methods=["GET","POST"])
def playoff_view():
    if active_tournament is None:
        return redirect("/")

    active_tournament.check_stage_progression()

    if request.method == "POST":
        web_manager.process_match_action(
            match_id=int(request.form.get("match_id")),
            action=request.form.get("action"),
            games_a=request.form.getlist("game_a[]"),
            games_b=request.form.getlist("game_b[]")
        )

        return redirect("/playoff")

    return render_template("playoff.html",
                           tournament = active_tournament,
                           web_manager=web_manager)

@app.route("/results")
def results():
    if active_tournament is None:
        return redirect("/")

    ranking = web_manager.get_final_ranking()
    return render_template("results.html",
                           tournament=active_tournament,
                           web_manager=web_manager,
                           ranking=ranking if ranking else [])

@app.route("/reset_settings", methods=["POST"])
def reset_settings():
    global active_tournament
    global web_manager
    session.pop("wizard_data", None)
    active_tournament= None
    web_manager = None

    return redirect("/settings_basic")

@app.route("/consolation_minigroup", methods=["GET", "POST"])
def consolation_minigroup():
    if active_tournament is None:
        return redirect("/")

    if request.method == "POST":
        web_manager.process_match_action(
            match_id=int(request.form.get("match_id")),
            action=request.form.get("action"),
            games_a=request.form.getlist("game_a[]"),
            games_b=request.form.getlist("game_b[]")
        )

        return redirect("/consolation_minigroup")

    # pokud je to GET požadavek, získáme data pomocí naší nové metody
    group_data = web_manager.get_groups_for_web(stage="consolation")

    return render_template("consolation_minigroup.html",
                            tournament= active_tournament,
                            web_manager=web_manager,
                            group_data = group_data)

@app.route("/consolation_playoff", methods=["POST", "GET"])
def consolation_playoff():
    if active_tournament is None:
        return redirect("/")

    # průběžně kontrolujeme, jestli se nám v turnaji něco neodemklo
    active_tournament.check_stage_progression()

    if request.method == "POST":
        web_manager.process_match_action(
            match_id=int(request.form.get("match_id")),
            action=request.form.get("action"),
            games_a=request.form.getlist("game_a[]"),
            games_b=request.form.getlist("game_b[]")
        )

        return redirect("/consolation_playoff")

    #Poslání dat pro vykreslení HTML
    playoff_data = web_manager.get_playoff_structure_for_web(branch_key= "consolation")
    return render_template("/consolation_playoff.html",
                           tournament = active_tournament,
                           web_manager=web_manager,
                           playoff_data= playoff_data)

if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0")