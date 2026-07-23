from setupwizard import SetupWizard
from player import Player
from group import Group
from playoff import Playoff
from results import Results


class Tournament:
    """
    Třída zodpovědná za celkovou orchestraci turnaje.
    Spravuje jeho fáze, drží strukturu větví,
    sleduje postup turnaje a pro výpočty statistik, pořadí a vyhodnocení skupin
    deleguje logiku na dedikovaný Results manager.
    """

    def __init__(self, setup: SetupWizard):
        # Základní identifikační a stavové atribudy turnaje
        self.results_manager = Results()
        self.name = setup.name
        self.tournament_format = setup.tournament_format
        self.raw_groups_data = setup.groups
        self.stage = "groups"  # Aktualní fáze turnaje (začíná se ve skupinách)
        self.match_counter = 1 # počítadlo zápasů

        # Struktura větví turnaje pro správu pavouků
        self.branches = {
            "main":None,  # Hlavní pavouk playoff
            "consolation":None, # útěcha
            "placement": {}  # dohrávkové zápasy o kontrétní umístění
        }
        self.eliminated_players = []

        #---- Pravidla turnaje načtená ze setupu ----
        self.group_match_format = setup.group_match_format
        self.advance_per_group = setup.advance_per_group
        self.elimination_actions = setup.group_elimination_actions
        self.playoff_match_format = setup.playoff_match_format
        self.playoff_elimination_action = setup.playoff_elimination_actions

        #Inicializace a transformace skupin
        transformed_groups_dict = {}
        for group_name,player_names in self.raw_groups_data.items():
            player_objects = []
            for name in player_names:
                # každému jménu vytvoříme plnohodnotný objekt hráče
                player_objects.append(Player(name=name))
            transformed_groups_dict[group_name]=player_objects

        # Vytvoření instance skupinové fáze a vygenerování zápasů
        self.group_stage = Group(
            groups_dict=transformed_groups_dict,
            match_format=self.group_match_format,
            stage_name="Group"
        )
        self.group_stage.generate_matches(self)

        #Reference na hlvní plaoff
        self.main_playoff = None


    def get_next_match_id(self):
        """
        Vrátí aktuální ID pro nový zápas a posune počítadlo o 1 dál.
        Zajišťuje, že každý zápas v celém turnaji má své jedinečné ID.
        :return:
        """

        current_id = self.match_counter
        self.match_counter+=1
        return current_id

    def check_stage_progression(self):
        """
        Kontoluje, zda nastal čas posunout turnaj ze skupinové fáze do playoff.
        - Pokud už playoff běží, vrací True.
        - Pokud jsou všechny zápasy ve skupinách dohrané, vrací True.
        - Jinak vrací False (skupiny stále probíhají)
        :return:
        """

        # pokud hlavní playoff již existuje, není co řešit
        if self.branches["main"] is not None:
            return True

        # Zkontrolujeme, zda jsou dohrané všechny zápasy ve všech skupinách
        if self.results_manager.are_groups_finished(self.group_stage):
            self.evaluate_group_stage_and_proceed()
            return True

        return False


    def evaluate_group_stage_and_proceed(self):
        """
        Vyhodnotí skončenou skupinovou fázi:
        1. Seřadí hráče v každé skupině.
        2. Rozdělí je na postupující a vyřazené (pro útěchu)
        3. Inicializuje hlavní playoff.
        4. Podle zvoleného pravidla vytvoří útěchovou skupinu (minitabulku) nebo utěchové  playoff
        :return:
        """


        advancing, all_eliminated = self.results_manager.evaluate_group_stage(
            self.group_stage, self.advance_per_group)


        # Vytvotříme hlavního pavouka pro postupující hráče
        self.main_playoff = Playoff(
            qualified_players=advancing,
            match_format=self.playoff_match_format,
            stage_name=self.stage,
            playoff_elimination_action=self.playoff_elimination_action
        )
        self.branches["main"] = self.main_playoff
        self.main_playoff.generate_first_round(self)
        print(advancing)

        # Reakce na vyřazené hráče podle zvolené konfigurace turnaje
        if self.elimination_actions == "minitabulka":
            minitabulka_dict = {"ÚTĚCHA": all_eliminated}
            self.consolation_group = Group(
                groups_dict=minitabulka_dict,
                match_format=self.group_match_format,
                stage_name=self.stage
            )
            self.consolation_group.generate_matches(self)

        elif self.elimination_actions == "playoff_b":
            self.consolation_playoff = Playoff(
                qualified_players=all_eliminated,
                match_format=self.playoff_match_format,
                stage_name=self.stage,
                playoff_elimination_action=self.playoff_elimination_action
            )
            self.branches["consolation"] = self.consolation_playoff
            self.consolation_playoff.generate_first_round(self)


    def get_groups_for_web(self):
        """
        Vrátí slovník skupin a jejich aktuální pořadí ve formátu vhodném pro webové zobrazení.
        Pro každého hrače vrací jméno a získané body.
        """
        return {
            name: [{"name":p.name,"points":p.group["points"]} for p in self.group_stage.rank_players(name)]
            for name in self.group_stage.groups.keys()
        }

    def get_playoff_structure_for_web(self,branch_key="main"):
        """
        Vrátí strukturu kol a zápasů pro danou větev playoff (pro vykreslení na webu)
        -brach_key: Klíč větve (např. "main", "consolation")
        """

        playoff = self.branches.get(branch_key)
        return playoff.rounds if playoff else None

    def is_tournament_fully_finished(self):
        """
        Zda je turnaj kompletně dohraný (včetně všech zápasů o umístění).
        Vrací True, pokud máme celkového vítěze a všechny dohrávkové zápasy jsou hotové
        :return:
        """

        # Pokud hlavní playoff nemá vítěze,turnaj neskončil
        if not (self.branches["main"] and self.branches["main"].winner):
            return False

        # Projdeme všechny dohrávkové pavouky a zkontrolujeme, zda mají všechny zápasy hotové.
        for key,playoff_obj in self.branches["placement"].items():
            for match in playoff_obj.matches:
                if not match.is_finished:
                    return False

        return True
