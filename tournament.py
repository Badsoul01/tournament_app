from player import Player
from group import Group
from playoff import Playoff

class Tournament:

    def __init__(self,name:str,groups_data_from_web:dict,settings_from_web:dict):
        self.name = name
        self.raw_groups_data = groups_data_from_web

        #---- Pravidla ----

        #Formáty zápasů
        self.group_match_format = settings_from_web.get("group_match_format","2 sets")
        self.playoff_match_format = settings_from_web.get("playoff_match_format","Best of 3")
        #pravidla pro postup a vyřazení
        self.advancing_per_group = settings_from_web.get("advancing_per_group",2)
        self.non_advancing_action = settings_from_web.get("non_advancing_action","KO")
        self.playoff_lossers_action = settings_from_web.get("playoff_lossers_action","KO")

        # ---- Objekty ----

        #1. základní skupiny

        transformed_groups_dict = {}
        for group_name,player_names in groups_data_from_web.items():
            player_objects = []
            for name in player_names:
                player_objects.append(Player(name=name))
            transformed_groups_dict[group_name]=player_objects

        self.group_stage = Group(groups_dict=transformed_groups_dict,match_format=self.group_match_format)
        self.group_stage.generate_matches()


        #2. hlavní vyřazovací část
        self.main_playoff = None
        self.placement_playoff = {}


        #3. Útěcha
        self.consolation_playoff = None
        self.consolation_placement_playoff = {}
        self.consolation_group = None


    def evaluate_group_stage_and_proceed(self):
        all_advancing = []
        all_eliminated = []

        for group_name in self.group_stage.groups.keys():
            sorted_players = self.group_stage.rank_players(group_name)

            all_advancing.extend(sorted_players[:self.advancing_per_group])
            all_eliminated.extend(sorted_players[self.advancing_per_group:])

        self.main_playoff = Playoff(qualified_players=all_advancing, match_format=self.playoff_match_format)
        self.main_playoff.generate_first_round()

        if self.non_advancing_action == "minitabulka":
            minitabulka_dict = {"ÚTĚCHA": all_eliminated}
            self.consolation_group = Group(groups_dict=minitabulka_dict,match_format=self.group_match_format)
            self.consolation_group.generate_matches()

        elif self.non_advancing_action == "playoff_b":
            self.consolation_playoff = Playoff(qualified_players=all_eliminated,match_format=self.playoff_match_format)
            self.consolation_playoff.generate_first_round()




    def check_tournament_status(self):
        if self.main_playoff and self.main_playoff.winner:
            return {
                "status":"finished",
                "winner": self.main_playoff.winner.name,
                "message": f"turnaj {self.name} skončil. Vítězem je {self.main_playoff.winner.name}"
            }
        return {
            "status": "running",
            "message": "Turnaj stále běží."
        }

    def create_placement_playoff(self,players:list,round_number:int,is_consolation_bracket: bool = False):
        """
        Vytvoří pavouka pro dohrávky,
        -round:number: určuje, o jakou pozici se hraje
        -is_consolation_bracket: Pokud True, ukládáme do consolation_placement_playoff
        """

        if round_number == 2:
            key = "3"
        elif round_number == 3:
            key = "5-8"
        else:
            key = f"pos_{len(players)}"

        new_playoff = Playoff(qualified_players=players,match_format=self.playoff_match_format)
        new_playoff.generate_first_round()

        if is_consolation_bracket:
            self.consolation_placement_playoff[key] = new_playoff
        else:
            self.placement_playoff[key]=new_playoff

        print(f"Vytvořen dohrávkový pavouk {key} pro {len(players)}  hráčů.")


    def get_groups_for_web(self):
        """Vrátí slovník skupin a jejich pořadí pro zobrazení."""
        return {
            name: [{"name":p.name,"points":p.group["points"]} for p in self.group_stage.rank_players(name)]
            for name in self.group_stage.groups.keys()
        }

    def get_playoff_structure_for_web(self,playoff_type="main"):
        """Vrátí strukturu pavouka"""
        playoff = self.main_playoff if playoff_type == "main" else self.consolation_playoff
        if not playoff:
            return None
        return playoff.rounds

    def get_final_ranking(self):
        """Vrátí seřazený list jmen pro finální tabulku."""
        ranking = []
        if self.main_playoff and self.main_playoff.winner:
            ranking.append(self.main_playoff.winner.name)
        return ranking

    
