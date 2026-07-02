from doctest import debug
from bs4 import BeautifulSoup
import requests
from flask import Flask,render_template,request



app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scrape", methods=["POST"])
def scrape():
    url = request.form.get("url").strip()
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

    return  render_template("players.html",players=players)


    return f"<h3> úspěšně přijato! Na pozadí budeme seškrabávat URL </h3> {url_z_formuláře}"

if __name__ == "__main__":
    app.run(debug=True)