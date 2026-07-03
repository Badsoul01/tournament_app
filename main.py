
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
    session["tables"] = {"A":[]}
    session["matches"] = {"A":[]}

    return  redirect("/rozrazeni")


@app.route("/rozrazeni")
def rozrazeni():
    all_tables = session.get('tables',{"A":[],"B":[]})
    free_players = session.get('players',[])

    generated_matches = session.get("matches",{"A":[],"B":[]})

    return render_template("players.html",
                           players=free_players,
                           tables=all_tables,
                           matches=generated_matches)

@app.route("/add_player",methods=["POST"])
def add_player():
    player_name = request.form.get("player_name")
    group = request.form.get("group")

    tables = session.get("tables",{})
    players = session.get("players",[])

    if group in tables and player_name in players:
        tables[group].append(player_name)
        players.remove(player_name)

        session['tables'] = tables
        session['players'] = players



    session.modified= True

    return  redirect("/rozrazeni")

@app.route("/generate_tournament", methods=["POST"])
def generate_tournament():
    all_tables = session.get("tables",{"A":[],"B":[]})
    new_match_order = {"A":[],"B":[]}

    for g_name,p_list in all_tables.items():
        doubles = list(combinations(p_list,2))
        random.shuffle(doubles)
        new_match_order[g_name]=doubles

    session["matches"] = new_match_order

    return redirect("/rozrazeni")

@app.route("/setup_groups",methods=["POST"])
def setup_groups():
    try:
        num_groups = int(request.form.get("num_groups",1))
    except ValueError:
        num_groups=1

    all_players = session.get("players",[])
    tables = session.get("tables",{})
    for p_list in tables.values():
        all_players.extend(p_list)

    session["players"] =list(set(all_players))

    new_tables = {}

    for i in range(num_groups):
        letter = chr(65+i)
        new_tables[letter]=[]

    session["tables"] = new_tables
    session["matches"] = {letter:[] for letter in new_tables.keys()}

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