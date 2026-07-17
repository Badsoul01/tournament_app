from setupwizard import SetupWizard
from player import Player
from group import Group
from playoff import Playoff

class Tournament:

    def __init__(self, setup: SetupWizard):
        self.name = setup.name
        self.tournament_format = setup.tournament_format
        self.raw_groups_data = setup.groups
        self.stage = "groups"

        self.branches = {
            "main":None,
            "consolation":None,
            "placement": {}
        }
        self.eliminated_players = []
        #---- Pravidla ----
        #1.Skupiny
        self.group_match_format = setup.group_match_format
        self.advance_per_group = setup.advance_per_group
        self.elimination_actions = setup.group_elimination_actions
        self.playoff_match_format = setup.playoff_match_format

        #Inicializace skupin
        transformed_groups_dict = {}
        for group_name,player_names in self.raw_groups_data.items():
            player_objects = []
            for name in player_names:
                player_objects.append(Player(name=name))
            transformed_groups_dict[group_name]=player_objects

        self.group_stage = Group(groups_dict=transformed_groups_dict,match_format=self.group_match_format,stage_name="Group")
        self.group_stage.generate_matches()


        #2.Playoff
        self.main_playoff = None

        self.playoff_elimination_action = setup.playoff_elimination_actions

    def evaluate_group_stage_and_proceed(self):
        all_advancing = []
        all_eliminated = []

        for group_name in self.group_stage.groups.keys():
            sorted_players = self.group_stage.rank_players(group_name)

            all_advancing.extend(sorted_players[:self.advance_per_group])
            all_eliminated.extend(sorted_players[self.advance_per_group:])

        all_advancing.sort(key=lambda p: p.get_sorting_stats("Group"), reverse=True)
        self.main_playoff = Playoff(qualified_players=all_advancing, match_format=self.playoff_match_format, stage_name=self.stage)
        self.branches["main"] = self.main_playoff
        self.main_playoff.generate_first_round()

        if self.elimination_actions == "minitabulka":
            minitabulka_dict = {"ÚTĚCHA": all_eliminated}
            self.consolation_group = Group(groups_dict=minitabulka_dict, match_format=self.group_match_format,stage_name=self.stage)
            self.consolation_group.generate_matches()

        elif self.elimination_actions == "playoff_b":

            self.consolation_playoff = Playoff(qualified_players=all_eliminated, match_format=self.playoff_match_format, stage_name=self.stage)
            self.branches["consolation"] = self.consolation_playoff
            self.consolation_playoff.generate_first_round()

    def check_tournament_status(self):
        if self.branches["main"] and self.branches["main"].winner:
            return {
                "status":"finished",
                "winner": self.branches["main"].winner.name,
                "message": f"turnaj {self.name} skončil. Vítězem je {self.branches["main"].winner.name}"
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

        stage = "Consolation_Placement" if is_consolation_bracket else "Main_placement"

        new_playoff = Playoff(qualified_players=players,match_format=self.playoff_match_format,stage_name=f"{stage}_{key}")
        new_playoff.generate_first_round()

        if "placement" not in self.branches:
            self.branches["placement"] = {}
        self.branches["placement"][key] = new_playoff

        print(f"Vytvořen dohrávkový pavouk {key} pro {len(players)}  hráčů.")


    def get_groups_for_web(self):
        """Vrátí slovník skupin a jejich pořadí pro zobrazení."""
        return {
            name: [{"name":p.name,"points":p.group["points"]} for p in self.group_stage.rank_players(name)]
            for name in self.group_stage.groups.keys()
        }

    def get_playoff_structure_for_web(self,branch_key="main"):
        """Vrátí strukturu pavouka"""
        playoff = self.branches.get(branch_key)
        return playoff.rounds if playoff else None

    def get_final_ranking(self):
        """Vrátí seřazený list jmen pro finální tabulku."""
        ranking = []
        if self.branches["main"] and self.branches["main"].winner:
            ranking.append(self.branches["main"].winner.name)

        for key in sorted(self.branches["placement"].keys()):
            p = self.branches["placement"][key]
            if p.winner:
                ranking.append(p.winner.name)

        return ranking

    def check_stage_progression(self):
        if self.branches["main"] is not None:
            return True

        if  all(self.group_stage.are_all_matches_played(g) for g in self.group_stage.groups):
                self.evaluate_group_stage_and_proceed()
                return True
        return False

