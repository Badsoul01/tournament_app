
import random
from bs4 import BeautifulSoup
import requests
from flask import Flask,render_template,request,session,redirect
from itertools import combinations

app = Flask(__name__)
app.secret_key = "ultra_tajny_klic"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scrape", methods=["POST"])
def scrape():
    url = request.form.get("url","").strip()
    if url.endswith("/"):
        url=url[:-1]

    if not url.endswith("/ucastnici"):
        url = f"{url}/ucastnici"

    players =[]
    try:
        r =requests.get(url,timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, features="html5lib")

        header = soup.find("h3",id=lambda x:x and x.startswith("participants-") and x!="participants-0")

        if header:
            container_div=header.find_next_sibling("div",class_="row d-flex flex-wrap")

            if container_div:
                players = [span.text.strip() for span in container_div.find_all("span")]

    except Exception as e:
        return f"<h3>Něco se pokazilo při načítání webu:</h3>{e}"

    if not players:
        return "<H3> na této URL nebyli nalezeni žádní účastníci. Zkontroluj odkaz.</h3>"

    session["players"] = players
    session["tables"] = {"A": {}}
    session["matches"] = {"A":{}}

    return  redirect("/rozrazeni")


@app.route("/rozrazeni")
def rozrazeni():
    all_tables = session.get('tables',{"A":{}})
    free_players = session.get('players',[])
    generated_matches = session.get("matches",{})
    played_matches = session.get("played_matches",{})

    return render_template("players.html",
                           players=free_players,
                           tables=all_tables,
                           matches=generated_matches,
                           played_matches=played_matches)

@app.route("/add_player",methods=["POST"])
def add_player():
    player_name = request.form.get("player_name")
    group = request.form.get("group")

    tables = session.get("tables",{})
    players = session.get("players",[])

    if group in tables and player_name in players:
        tables[group][player_name]={
            "body":0,
            "sety_w":0,
            "sety_l":0,
            "micky_w":0,
            "micky_l":0
        }
        players.remove(player_name)

        session['tables'] = tables
        session['players'] = players
        session.modified= True


    return  redirect("/rozrazeni")

@app.route("/generate_tournament", methods=["POST"])
def generate_tournament():
    all_tables = session.get("tables",{})
    new_match_order = {}

    for g_name,p_dict in all_tables.items():
        new_match_order[g_name]=[]
        p_list = list(p_dict.keys())
        doubles = list(combinations(p_list,2))
        random.shuffle(doubles)

        match_objects= []
        for idx,pair in enumerate(doubles):
            match_objects.append({
                "id": f"{g_name}_{idx}",
                "p1":pair[0],
                "p2":pair[1]
            })
        new_match_order[g_name] = match_objects

    session["matches"]= new_match_order
    session["played_matches"] = {g:[] for g in all_tables.keys()}
    session.modified = True

    return redirect("/rozrazeni")

@app.route("/record_score",methods=["POST"])
def record_score():
    group = request.form.get("group")
    match_id = request.form.get("match_id")

    try:
        s1 = int(request.form.get("s1",0))
        s2 = int(request.form.get("s2",0))
        m1 = int(request.form.get("m1",0))
        m2 = int(request.form.get("m2",0))
    except ValueError:
        return "Zadej platná čísla pro sety a míčky!",400

    matches = session.get("matches",{})
    played_matches = session.get("played_matches",{})
    tables = session.get("tables",{})

    active_matches = matches.get(group,[])
    current_match = None

    for m in active_matches:
        if m["id"] == match_id:
            current_match = m
            break

    if current_match:
        p1,p2 = current_match["p1"], current_match["p2"]

        tables[group][p1]["body"] +=s1
        tables[group][p1]["sety_w"] +=s1
        tables[group][p1]["sety_l"] +=s2
        tables[group][p1]["micky_w"] += m1
        tables[group][p1]["micky_l"] += m2

        tables[group][p2]["body"] += s2
        tables[group][p2]["sety_w"] += s2
        tables[group][p2]["sety_l"] += s1
        tables[group][p2]["micky_w"] += m2
        tables[group][p2]["micky_l"] += m1

        current_match["s1"]= s1
        current_match["s2"]= s2

        played_matches[group].append(current_match)
        active_matches.remove(current_match)

        session["tables"]= tables
        session["matches"]=matches
        session["played_matches"]=played_matches
        session.modified= True

    return redirect("/rozrazeni")






@app.route("/setup_groups",methods=["POST"])
def setup_groups():
    try:
        num_groups = int(request.form.get("num_groups",1))
    except ValueError:
        num_groups=1

    all_players = session.get("players",[])
    tables = session.get("tables",{})

    for group_content in tables.values():
        if isinstance(group_content,dict):
            all_players.extend(group_content.keys())
        else:
            all_players.extend(group_content)

    session["players"] = list(set(all_players))

    new_tables = {}
    for i in range(num_groups):
        letter = chr(65+i)
        new_tables[letter]={}

    session["tables"] = new_tables
    session["matches"]= {letter:[] for letter in new_tables.keys()}
    session["played_matches"]={letter:[] for letter in new_tables.keys()}


    session.modified = True
    return redirect("/rozrazeni")

@app.route("/delete_player", methods=["POST"])
def delete_player():
    player_name = request.form.get("player_name")

    players = session.get("players",[])
    tables = session.get("tables",{})

    if player_name in players:
        players.remove(player_name)

    for group_name,p_list in tables.items():
        if player_name in p_list:
            p_list.remove(player_name)

    session["players"] = players
    session["tables"] =tables
    session.modified = True

    return redirect("/rozrazeni")



@app.route("/add_custom_player", methods=["POST"])
def add_custom_player():
    player_name = request.form.get("player_name","").strip()
    if player_name:
        actual_players = session.get('players',[])

        actual_players.append(player_name)

        session['players'] = actual_players

    return redirect("/rozrazeni")


if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0")