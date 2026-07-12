from bs4 import BeautifulSoup
import requests
from datetime import date
from config import RULES_OPTIONS

class SetupWizard:

    def __init__(self):
        #základní informace
        self.name = ""
        self.date = date.today().strftime("%Y-%m-%d")
        self.min_groups = RULES_OPTIONS["min_group_size"]
        self.max_groups = RULES_OPTIONS["max_group_size"]
        self.players = []
        self.groups = {}
        self.total_groups = 0


        #formát zápasů
        self.group_match_format = "2"
        self.playoff_match_format = "BO3"

        #pravidla postupu
        self.advancing_per_group = RULES_OPTIONS["advance_per_group"][0]
        self.players_per_group_limit = RULES_OPTIONS["players_per_group_limit"][0]

        #akce
        self.non_advancing_action = "playoff_b"
        self.playoff_losers_action = "consolation"


    def create_groups(self,target_count:int):
        current_count = self.total_groups
        diff = target_count - current_count
        if diff > 0 and current_count<=RULES_OPTIONS["max_group_size"]:
            for i in range(current_count,target_count):
                letter = chr(65+i)
                self.total_groups+=1
                self.groups[letter]=[]
        else:
            print("Maximální povolené množství skupin.")


    def add_players(self,names:str):
        players = names.replace("\n",",").split(",")
        added_count = 0
        for player in players:
            clear_name = player.strip().title()
            if clear_name  and clear_name not in self.players:
                self.players.append(clear_name)
                added_count += 1

        return added_count>0

    def scrapped_url(self,url):
        url = url.strip()
        if url.endswith("/"):
            url = url[:-1]

        if not url.endswith("/ucastnici"):
            url = f"{url}/ucastnici"

        players = []
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.content, features="html5lib")

            header = soup.find("h3", id=lambda x: x and x.startswith("participants-") and x != "participants-0")

            if header:
                container_div = header.find_next_sibling("div", class_="row d-flex flex-wrap")

                if container_div:
                    players = [span.text.strip() for span in container_div.find_all("span")]
                    self.add_players(", ".join(players))

        except Exception as e:
            return None

