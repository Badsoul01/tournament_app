from bs4 import BeautifulSoup
import requests
from config import TOURNAMENT_FORMAT,GROUPS_RULES, PLAYOFF_RULES
from datetime import datetime
import random
from app.services.utils.queries import get_players_ranking_map


class SetupWizard:

    def __init__(self):
        # =========================================================
        # ZÁKLADNÍ INFORMACE O TURNAJI
        # =========================================================

        self.name = ""
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.location = ""

        self.tournament_format = TOURNAMENT_FORMAT[0]
        self.include_in_global_stats = True

        # =========================================================
        # HRÁČI
        # =========================================================

        self.players = []

        # =========================================================
        # SKUPINY
        # =========================================================

        self.min_groups = GROUPS_RULES["min_group"]
        self.max_groups = GROUPS_RULES["max_group"]

        self.min_players_per_group = GROUPS_RULES["min_players_per_group"]
        self.max_players_per_group = GROUPS_RULES["max_players_per_group"]

        self.group_match_format = 2

        self.advance_per_group = GROUPS_RULES["advance_per_group"][0]

        self.group_elimination_action = "playoff_b"
        self.groups = {}

        # =========================================================
        # JEDNA SKUPINA
        # =========================================================

        self.single_group_max_players = (
            GROUPS_RULES["single_group"]["max_players"]
        )

        self.single_group_playoff_count = 0

        self.single_group_playoff_players = (
            GROUPS_RULES["single_group"]["playoff_players"]
        )

        # =========================================================
        # PLAYOFF
        # =========================================================

        self.players_allowed_to_playoff = (
            PLAYOFF_RULES["players_allowed_to_playoff"]
        )

        self.playoff_match_format = 3

        self.playoff_elimination_action = "consolation"


    @property
    def total_groups(self):
        return len(self.groups)

    @property
    def is_single_group(self):
        return self.total_groups == 1

    @property
    def total_tournament_players(self):
        """ Vratí celkový počet všech hráčů (nezařazení + zařazení ve skupinách)."""
        assigned_count = sum(
            len(group_players)
            for group_players in self.groups.values()
        )
        return self.non_classification_players + assigned_count

    @property
    def non_classification_players(self):
        return len(self.players)

    @property
    def total_players_advance_to_playoff(self):
        if self.is_single_group:
            return self.single_group_playoff_count

        return sum(
            min(len(group_players), self.advance_per_group)
            for group_players in self.groups.values()
        )


    @property
    def has_empty_group(self):
        """Vrací True, pokud existuje alespoň jedna prázdná skupina."""
        return any(
            len(players) == 0
            for players in self.groups.values())

    @property
    def current_group_player_limit(self):
        if self.is_single_group:
            return self.single_group_max_players

        return self.max_players_per_group


    def total_players_in_group(self,letter):
        return len(self.groups.get(letter,[]))

    def create_groups(self,count_to_add:int) -> bool:
        created = False
        original_group_count = self.total_groups

        for _ in range(count_to_add):
            if self.total_groups>= self.max_groups:
                break

            letter = chr(65+self.total_groups)
            self.groups[letter]=[]
            created = True

        if original_group_count == 1 and self.total_groups == 2:
            self._split_single_group()

        return created



    def get_all_current_player_names(self):
        """
        Vratí množinu (set) všech jmen hrůčů aktuálně přidaných ve wizardu
        (tj. v nezařazených, tak zapsaných v jednotlivých skupinách)
        """

        all_names = set(self.players)
        for group_players in self.groups.values():
            all_names.update(group_players)
        return all_names

    def add_players(self,names:str):
        players = names.replace("\n",",").split(",")


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

    def scrapped_url(self, url):
        url = url.strip()

        # Vynutíme českou verzi URL (odstraníme anglickou mutaci)
        url = url.replace("/en/event", "/udalost")

        if url.endswith("/"):
            url = url[:-1]

        event_url = url
        participants_url = f"{event_url}/ucastnici"


        imported = {
            "name": None,
            "location": None,
            "date": None,
            "players_added": 0,
        }

        try:
            # Přidáme hlavičku prohlížeče, aby server neodmítl Python bota
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

            # Hlavní stránka události
            event_response = requests.get(
                event_url,
                headers=headers,
                timeout=10
            )
            event_response.raise_for_status()

            event_soup = BeautifulSoup(
                event_response.content,
                features="html5lib"
            )

            # místo konání
            location_icon = event_soup.find(
                "img",
                alt="Místo konání"
            )
            if location_icon:
                location_item = location_icon.find_parent("li")

                if location_item:
                    location_link = location_item.find("a")

                    if location_link:
                        location = location_link.get_text(strip=True)

                        self.location = location
                        imported["location"]= location

            # název akce
            title = event_soup.find("h1")

            if title:
                name = title.get_text(strip=True)
                name = name.replace("ve stolním tenise", "")
                name = " ".join(name.split())

                self.name = name
                imported["name"] = name

            # datum konání
            start_label = event_soup.find(
                "th",
                string=lambda value: value and value.strip() == "Začátek akce"
            )
            if start_label:
                start_value = start_label.find_next_sibling("td")

                if start_value:
                    raw_date = start_value.get_text(strip=True)

                    event_datetime = datetime.strptime(
                        raw_date,
                        "%d.%m.%Y %H:%M"
                    )
                    date = event_datetime.strftime("%Y-%m-%d")

                    self.date = date
                    imported["date"] = date

            # Účastníci
            r = requests.get(participants_url, headers=headers, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.content, features="html5lib")


            header = soup.find("h3", id=lambda x: x and x.startswith("participants-") and x != "participants-0")

            if header:
                container_div = header.find_next_sibling("div", class_="row d-flex flex-wrap")

                if container_div:
                    players = [span.text.strip() for span in container_div.find_all("span")]

                    before_count = self.total_tournament_players

                    self.add_players(", ".join(players))

                    after_count = self.total_tournament_players

                    imported["players_added"] = (
                        after_count - before_count
                    )

                return imported


        except Exception as e:
            # Zabráníme tichému selhání
            print(f"DEBUG: Chyba při stahování URL ({url}): {e}")
            return None


    def assign_player_to_group(self,player_name, group_letter):
        if player_name not in self.players:
            return False

        if group_letter not in self.groups:
            return False

        if len(self.groups[group_letter]) >= self.current_group_player_limit:
            return False

        self.players.remove(player_name)
        self.groups[group_letter].append(player_name)
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
            return False

        if len(self.groups[group_letter])>0 and not force:
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

        return True

    def clear_all_groups(self):
        """Smaže všechny skupiny naráz a vrátí všechny hráče do nezařazených."""
        for players in self.groups.values():
            for player in players:
                if player not in self.players:
                    self.players.append(player)

        self.groups = {}


    def import_to_dict(self):
        return self.__dict__.copy()

    def import_from_dict(self,data_dict):
        for key,value in data_dict.items():
            if key in self.__dict__:
                setattr(self,key,value)

    def check_readiness(self):
        if not self.name:
            return False

        if self.total_tournament_players == 0:
            return False

        if self.total_groups < self.min_groups:
            return False

        if self.non_classification_players > 0:
            return False

        # Každá skupina musí splnit pouze základní minimum hráčů
        for group_players in self.groups.values():
            if len(group_players) < self.min_players_per_group:
                return False

        # =========================================================
        # JEDNA SKUPINA
        # =========================================================
        if self.is_single_group:
            player_count = len(next(iter(self.groups.values())))

            # 0 = turnaj končí skupinou
            if self.single_group_playoff_count == 0:
                return True

            if self.single_group_playoff_count not in self.single_group_playoff_players:
                return False

            if self.single_group_playoff_count > player_count:
                return False

            if self.single_group_playoff_count not in self.players_allowed_to_playoff:
                return False

            return True

        # =========================================================
        # VÍCE SKUPIN
        # =========================================================

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
        errors = []

        if not self.name:
            errors.append("Chybí název turnaje.")

        if self.total_tournament_players == 0:
            errors.append("V turnaji nejsou žádní hráči.")

        if self.total_groups < self.min_groups:
            errors.append(
                f"Nedostatečný počet skupin (minimum je {self.min_groups})."
            )

        if self.non_classification_players > 0:
            errors.append(
                f"Máš {self.non_classification_players} nezařazených hráčů "
                "(všichni musí být ve skupině)."
            )

        # Základní kontrola skupin
        for letter, group_players in self.groups.items():
            if len(group_players) < self.min_players_per_group:
                errors.append(
                    f"Skupina {letter} má málo hráčů "
                    f"({len(group_players)}), minimum je "
                    f"{self.min_players_per_group}."
                )

        # =========================================================
        # JEDNA SKUPINA
        # =========================================================
        if self.is_single_group:
            player_count = len(next(iter(self.groups.values())))

            if (
                    self.single_group_playoff_count
                    not in self.single_group_playoff_players
            ):
                errors.append(
                    "Zvolený počet hráčů do playoff není povolený."
                )

            elif self.single_group_playoff_count > player_count:
                errors.append(
                    f"Do playoff nemůže postoupit "
                    f"{self.single_group_playoff_count} hráčů, "
                    f"když je ve skupině pouze {player_count}."
                )

            elif (
                    self.single_group_playoff_count > 0
                    and self.single_group_playoff_count
                    not in self.players_allowed_to_playoff
            ):
                errors.append(
                    f"Počet postupujících "
                    f"({self.single_group_playoff_count}) "
                    "nelze nasadit do pavouka."
                )

            return errors

        # =========================================================
        # VÍCE SKUPIN
        # =========================================================
        if (
                self.total_groups > 1
                and self.total_players_advance_to_playoff
                not in self.players_allowed_to_playoff
        ):
            errors.append(
                f"Počet postupujících "
                f"({self.total_players_advance_to_playoff}) "
                "nelze nasadit do pavouka."
            )

        return errors

    def auto_seed_players(
            self,
            ranking_map,
            seed_criterion,
            seed_mode="auto_groups",

    ):
        # =========================================================
        # 1. PŘÍPRAVA HRÁČŮ A SKUPIN
        # =========================================================

        if seed_mode == "auto_groups":
            # Vezmeme všechny hráče - jak nezařazené,
            # tak ty, kteří už jsou ve skupinách.
            all_players = list(self.get_all_current_player_names())

            self.players = all_players
            self.groups = {}

            total_players = len(all_players)

            # Počet skupin počítáme směrem dolů,
            # aby nevznikaly skupiny s méně než minimem hráčů.
            target_groups_count = (
                    total_players // self.min_players_per_group
            )

            target_groups_count = max(
                self.min_groups,
                min(target_groups_count, self.max_groups)
            )

            self.create_groups(target_groups_count)

        elif seed_mode == "reset_existing":
            # Zachováme počet existujících skupin,
            # ale všechny hráče vrátíme mezi nezařazené.
            all_players = list(self.get_all_current_player_names())

            self.players = all_players

            for letter in self.groups:
                self.groups[letter] = []

        elif seed_mode == "fill_existing":
            # Existující rozdělení necháme být.
            # Pracujeme pouze s hráči v self.players.
            pass

        else:
            return False

        # =========================================================
        # 2. KONTROLA SKUPIN A HRÁČŮ
        # =========================================================

        if self.total_groups == 0:
            return False

        unassigned_players = list(self.players)

        if not unassigned_players:
            return False

        # =========================================================
        # 3. SEŘAZENÍ HRÁČŮ PODLE RANKINGU
        # =========================================================

        if seed_criterion == "random":
            sorted_unassigned = list(unassigned_players)
            random.shuffle(sorted_unassigned)
        else:
            def get_rank(name):
                return ranking_map.get(name, float("inf"))

            sorted_unassigned = sorted(
                unassigned_players,
                key=get_rank
            )

        # =========================================================
        # 4. NASAZENÍ TOP HRÁČŮ
        # =========================================================

        # TOP hráče chceme dávat pouze do prázdných skupin.
        # U fill_existing tedy nebudeme sahat na už obsazené skupiny.
        empty_group_letters = [
            letter
            for letter, group_players in self.groups.items()
            if len(group_players) == 0
        ]

        top_count = min(
            len(empty_group_letters),
            len(sorted_unassigned)
        )

        top_players = sorted_unassigned[:top_count]
        remaining_players = sorted_unassigned[top_count:]

        for index, player in enumerate(top_players):
            target_group = empty_group_letters[index]

            self.assign_player_to_group(
                player_name=player,
                group_letter=target_group
            )

        # =========================================================
        # 5. NÁHODNÉ ROZDĚLENÍ ZBYTKU
        # =========================================================

        random.shuffle(remaining_players)

        for player in remaining_players:
            available_groups = [
                (letter, len(group_players))
                for letter, group_players in self.groups.items()
                if len(group_players) < self.current_group_player_limit
            ]

            if not available_groups:
                break

            # Hráče vždy pošleme do aktuálně nejméně zaplněné skupiny.
            available_groups.sort(
                key=lambda item: item[1]
            )

            target_group = available_groups[0][0]

            self.assign_player_to_group(
                player_name=player,
                group_letter=target_group
            )

        return True

    def process_form_action(self, form_data):
        action = form_data.get("action")

        if action == "add_players":
            player_text = form_data.get("players_text")
            if player_text:
                self.add_players(names=player_text)

        elif action == "increase_groups":
            self.create_groups(count_to_add=1)

        elif action == "decrease_groups":
            if self.groups:
                # Najdeme od konce abecedy první skupinu, která je prázdná
                target_group = None

                for letter in reversed(sorted(self.groups.keys())):
                    if len(self.groups[letter]) == 0:
                        target_group = letter
                        break

                if target_group:
                    self.remove_group(
                        group_letter=target_group,
                        force=False
                    )

        elif action == "seed_players":
            criterion = form_data.get(
                "seed_criterion",
                "last_tournament"
            )

            seed_mode = form_data.get(
                "seed_mode",
                "auto_groups"
            )

            if criterion == "random":
                ranking_map = {}
            else:
                ranking_map = get_players_ranking_map(criterion)

            self.auto_seed_players(
                ranking_map=ranking_map,
                seed_mode=seed_mode,
                seed_criterion=criterion
            )

        elif action == "assign_players":
            player_name = form_data.get("player_name")
            group_letter = form_data.get("group_letter")

            if player_name and group_letter:
                self.assign_player_to_group(
                    player_name=player_name,
                    group_letter=group_letter
                )

        elif action == "remove_player":
            player_name = form_data.get("player_name")

            if player_name:
                self.remove_player(
                    player_name=player_name
                )

        elif action == "remove_single_group":
            letter = form_data.get("group_letter")
            force = form_data.get("force") == "true"

            self.remove_group(
                group_letter=letter,
                force=force
            )

        elif action == "reset_all_groups":
            self.clear_all_groups()

        elif action == "scrap_players":
            url = form_data.get("scrap_url")

            if url:
                 return self.scrapped_url(
                    url=url
                )

        elif action == "update_base_settings":
            name = form_data.get("name")
            date = form_data.get("date")
            location = form_data.get("location")
            tournament_format = form_data.get("tournament_format")

            if name is not None:
                self.name = name.strip()

            if date:
                self.date = date

            if location is not None:
                self.location = location.strip()

            if tournament_format in TOURNAMENT_FORMAT:
                self.tournament_format = tournament_format

            self.include_in_global_stats = (
                    form_data.get("include_in_global_stats") == "true"
            )

        elif action == "update_group_settings":
            group_match_format = form_data.get("group_match_format")

            if group_match_format and group_match_format.isdigit():
                self.group_match_format = int(group_match_format)

            advance_value = form_data.get("advance_per_group")

            if advance_value and advance_value.isdigit():
                self.advance_per_group = int(advance_value)

            single_value = form_data.get("single_group_playoff_count")

            if single_value and single_value.isdigit():
                self.single_group_playoff_count = int(single_value)

            group_elimination_action = form_data.get(
                "group_elimination_action"
            )

            if group_elimination_action:
                self.group_elimination_action = group_elimination_action

            # Jedna skupina + Bez playoff = turnaj končí skupinou.
            if (
                    self.is_single_group
                    and self.single_group_playoff_count == 0
            ):
                self.group_elimination_action = "KO"

        elif action == "update_playoff_settings":
            playoff_match_format = form_data.get(
                "playoff_match_format"
            )

            if (
                    playoff_match_format
                    and playoff_match_format.isdigit()
            ):
                self.playoff_match_format = int(
                    playoff_match_format
                )

            playoff_elimination_action = form_data.get(
                "playoff_elimination_action"
            )

            if playoff_elimination_action:
                self.playoff_elimination_action = (
                    playoff_elimination_action
                )


        elif action == "next":
            self.clean_empty_groups()

    def _split_single_group(self):
        if self.total_groups != 2:
            return
        group_a = self.groups.get("A", [])
        group_b = self.groups.get("B", [])

        if group_b:
            return

        split_index =(len(group_a)+1) // 2

        self.groups["A"] = group_a[:split_index]
        self.groups["B"] = group_a[split_index:]
