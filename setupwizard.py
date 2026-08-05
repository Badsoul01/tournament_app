from bs4 import BeautifulSoup
import requests
from datetime import date

import group
from config import TOURNAMENT_RULES, GROUPS_RULES, PLAYOFF_RULES, STATE_OF_WIZARD

class SetupWizard:

    def __init__(self):
        self.state = STATE_OF_WIZARD[0]
        #základní informace
        self.name = ""
        self.date = date.today().strftime("%Y-%m-%d")
        self.tournament_format = TOURNAMENT_RULES["available_formats"]["groups_and_playoff"]
        self.selected_format= ""

        #skupiny
        self.min_groups = GROUPS_RULES["min_group"]
        self.max_groups = GROUPS_RULES["max_group"]
        self.group_creation_options = GROUPS_RULES["group_creation_options"][0]
        self.min_advance_per_group = GROUPS_RULES["min_advance_per_group"]
        self.max_advance_per_group = GROUPS_RULES["max_advance_per_group"]
        self.min_players_per_group = GROUPS_RULES["min_players_per_group"]
        self.max_players_per_group = GROUPS_RULES["max_players_per_group"]
        self.group_match_format = GROUPS_RULES["group_match_format"][2]
        self.advance_per_group = GROUPS_RULES["advance_per_group"][0]
        self.group_elimination_actions = GROUPS_RULES["elimination_actions"]["playoff_b"]
        self.players = []
        self.groups = {}

        #playoff
        self.players_allowed_to_playoff = PLAYOFF_RULES["players_allowed_to_playoff"]
        self.playoff_match_format = PLAYOFF_RULES["playoff_match_format"][3]
        self.playoff_elimination_action = PLAYOFF_RULES["elimination_actions"]["consolation"]


    @property
    def total_groups(self):
        return len(self.groups)

    @property
    def total_tournament_players(self):
        """ Vratí celkový počet všech hráčů (nezařazení + zařazení ve skupinách)."""
        assigned_count = sum(len(group_players) for group_players in self.groups.values())
        return self.non_classification_players + assigned_count

    @property
    def non_classification_players(self):
        return len(self.players)

    @property
    def total_players_advance_to_playoff(self):
        advance_players = sum(len(group_players[:self.advance_per_group]) for group_players in self.groups.values())
        return advance_players

    def total_players_in_group(self,letter):
        return len(self.groups.get(letter,[]))

    def create_groups(self,count_to_add:int):
        for _ in range(count_to_add):
            if self.total_groups<self.max_groups:
                letter = chr(65+self.total_groups)
                self.groups[letter]=[]
        else:
            print("Maximální povolené množství skupin.")


    def add_players(self,names:str):
        players = names.replace("\n",",").split(",")
        added_count = 0

        for player in players:
            clear_name = player.strip().title()

            if not clear_name:
                continue

            # Kontrola 1: je hráč v neřařazených hráčích?
            if clear_name in self.players:
                continue



            # Kontrola 2: je hráč už v nějaké skupině?
            is_in_any_group = any(clear_name in group_players for group_players in self.groups.values())

            if is_in_any_group:
                continue

             # Pokud nikde není, přidáme ho
            self.players.append(clear_name)

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


    def assign_player_to_group(self,player_name, group_letter):
        if player_name not in self.players:
            print(f"Hráč {player_name} není na volném seznamu hráčů.")
            return False

        if group_letter not in self.groups:
            print(f"Skupina {group_letter} neexistuje.")
            return False

        if len(self.groups[group_letter]) >= self.max_players_per_group:
            print(f"Skupina {group_letter} je plná.")
            return False

        self.players.remove(player_name)
        self.groups[group_letter].append(player_name)
        print(f"Hráč {player_name} byl přidán do skupiny {group_letter}.")
        return True

    def remove_player(self,player_name):
        for letter, group_list in self.groups.items():
            if player_name in group_list:
                group_list.remove(player_name)
                self.players.append(player_name)
                return True

        if player_name in self.players:
            self.players.remove(player_name)
            return True

        return False

    def remove_group(self,group_letter,force=False):
        if group_letter not in self.groups:
            print(f"Skupina {group_letter} neexistuje.")
            return False

        if len(self.groups[group_letter])>0 and not force:
            print(f"Skupina {group_letter} není prázdná!")
            return False

        if force:
            for player in self.groups[group_letter]:
                self.players.append(player)

        del self.groups[group_letter]


        new_groups = {}
        for i,(key,players) in enumerate(sorted(self.groups.items())):
            new_letter = chr(65+i)
            new_groups[new_letter] = players

        self.groups = new_groups

        print(f"Skupina {group_letter} byla smazána.")
        return True


    def import_to_dict(self):
        return self.__dict__.copy()

    def import_from_dict(self,data_dict):
        for key,value in data_dict.items():
            if key in self.__dict__:
                setattr(self,key,value)

    def check_readiness(self):
        """
        Kontrola zda je vše připraveno pro generování... Vrací true pokud jsou splněny všechny podmínky,jinak False.

        """
        # 2. Samotná kotrola:
        if not self.name:
            return False

        if self.total_tournament_players == 0:
            return False

        if self.non_classification_players >0:
            return False

        for letter,group_players in self.groups.items():
            if len(group_players) == 0 and self.non_classification_players == 0:
                continue

            if len(group_players) <self.min_players_per_group:
                return False

        if self.total_players_advance_to_playoff not in self.players_allowed_to_playoff:
            return False

        return True

    def clean_empty_groups(self):
        # Smaže prázdné skupiny, jen pokud nejsou volní hráči.
        if self.non_classification_players == 0:
            while True:
                empty_group = None
                for letter, players in self.groups.items():
                    if len(players) == 0:
                        empty_group = letter
                        break
                if empty_group:
                    self.remove_group(empty_group)
                else:
                    break


    def get_readiness_errors(self):
        """
        Projde podmínky připravenosti a vratí seznam konkrétních chyb.
        """
        # generování seznamu chyb pro uživatele
        errors = []

        if not self.name:
            errors.append("Chybí název turnaje.")

        if self.total_groups < self.min_groups:
            errors.append(f"Nedostatečný počet skupin (minimum je {self.min_groups}).")

        if self.non_classification_players  > 0:
            errors.append(f"Máš {self.non_classification_players} nezařazených hráčů (všichni musí být ve skupině).")

        if self.total_tournament_players == 0:
            errors.append(f"V turnaji nejsou žádní hráči.")


        for letter, group_players in self.groups.items():
            if len(group_players) < self.min_players_per_group:

                # Pokud je ve sekupině méně lidí než je povolené množství,
                # vypíše se klasická chyba o nedostatečném počtu hráčů.
                errors.append(f" Skupina {letter} má málo hráčů ({len(group_players)}) (minimum pro skupinu je {self.min_players_per_group}).")

        if self.total_players_advance_to_playoff not in self.players_allowed_to_playoff:
            errors.append(f"Počet postupujících ({self.total_players_advance_to_playoff}) nelze nasadit do pavouka.")

        return errors




