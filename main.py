from flask import Flask,render_template,request,redirect,session
from config import TOURNAMENT_RULES, GROUPS_RULES, PLAYOFF_RULES, STATE_OF_WIZARD
from setupwizard import SetupWizard
from tournament import Tournament

app = Flask(__name__)
app.secret_key = "Ultra tajny kod"
active_tournament = None

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
        print(f"DEBUG:Form data: {request.form}")

        if action == "add_players":
            player_text = request.form.get("players_text")
            if player_text:
                wizard.add_players(player_text)

        if action == "create_groups":
            count= int(request.form.get("groups_count"))
            wizard.create_groups(count)

        if action == "assign_players":
            player_name = request.form.get("player_name")
            group_letter = request.form.get("group_letter")
            if player_name and group_letter:
                wizard.assign_player_to_group(player_name=player_name,group_letter=group_letter)

        if action == "remove_player":
            player_name = request.form.get("player_name")
            if player_name:
                wizard.remove_player(player_name)

        if action == "remove_group":
            group_letter = request.form.get("group_letter")
            wizard.remove_group(group_letter)

        if action == "scrap_players":
            url = request.form.get("scrap_url")
            if url:
                wizard.scrapped_url(url)

        session["wizard_data"] = wizard.import_to_dict()

        if action == "back":
            return redirect("/settings_basic")
        if action == "next":


            wizard.group_match_format = request.form.get("group_match_format")
            value = request.form.get("advance_per_group")
            if value:
                print(value)
                wizard.advance_per_group= int(value)
            wizard.group_elimination_actions = request.form.get("group_elimination_actions")
            wizard.state = STATE_OF_WIZARD[2]
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
            wizard.playoff_elimination_actions = request.form.get("elimination_actions")
            global active_tournament
            active_tournament = Tournament(wizard)

            return redirect("/groups")



    return render_template("settings_playoff.html",
                           wizard=wizard,
                           PLAYOFF_RULES=PLAYOFF_RULES)


@app.route("/groups", methods=["GET", "POST"])
def update_match():
    if active_tournament is None:
        return redirect("/")
    if request.method == "POST":
        action = request.form.get("action")
        if action == "go_to_playoff":
            active_tournament.check_stage_progression()
            return redirect("/playoff")

        match_id = int(request.form.get("match_id"))
        games_a = request.form.getlist("game_a[]")
        games_b = request.form.getlist("game_b[]")

        played_sets =[]
        for a,b in zip(games_a,games_b):
            if a != "" and b != "":
                played_sets.append((int(a),int(b)))


        found_match = None

        for group_name,matches in active_tournament.group_stage.group_matches.items():
            for match in matches:
                if match.match_id ==match_id:
                    found_match =match
                    break

        if found_match:
            found_match.evaluate_match(played_sets)
            active_tournament.check_stage_progression()

        return redirect("/groups")

    return render_template("groups.html",tournament=active_tournament)


@app.route("/playoff", methods=["GET","POST"])
def playoff_view():
    if active_tournament is None:
        return redirect("/")

    active_tournament.check_stage_progression()

    if request.method == "POST":
        action= request.form.get("action")
        if action == "submit_result":
            match_id = int(request.form.get("match_id"))
            games_a = request.form.getlist("game_a[]")
            games_b = request.form.getlist("game_b[]")

            played_sets = []
            for a, b in zip(games_a, games_b):
                if a != "" and b != "":
                    played_sets.append((int(a), int(b)))


            current_playoff = active_tournament.branches["main"]
            found_match = None
            if current_playoff.current_round_number in current_playoff.rounds:
                matches = current_playoff.rounds[current_playoff.current_round_number]
                found_match = next((m for m in matches if m.match_id == match_id),None)

            if not found_match:
                for bracket_name in current_playoff.placement_rounds:
                    matches = current_playoff.placement_rounds[bracket_name]["matches"]
                    found_match= next((m for m in matches if m.match_id== match_id),None)
                    if found_match: break

            if found_match:
                found_match.evaluate_match(played_sets)
                print(f"DEBUG: Zápas {match_id} vyhodnocen, volám check_and_proceed()...")
                current_playoff.check_and_proceed(tournament=active_tournament)

            return redirect("/playoff")

    return render_template("playoff.html",tournament = active_tournament)


@app.route("/results")
def results():
    if active_tournament is None:
        return redirect("/")

    ranking = active_tournament.get_final_ranking()
    return render_template("results.html",
                           tournament=active_tournament,
                           ranking=ranking if ranking else [])

@app.route("/reset_settings", methods=["POST"])
def reset_settings():
    global active_tournament
    session.pop("wizard_data", None)

    active_tournament= None

    return redirect("settings_basic")


if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0")