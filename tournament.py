from setupwizard import SetupWizard
from player import Player
from group import Group
from playoff import Playoff
from results import Results
from match import Match
from seedingengine import SeedingEngine

class Tournament:
    """
    Třída zodpovědná za celkovou orchestraci turnaje.
    Spravuje jeho fáze, drží strukturu větví,
    sleduje postup turnaje a pro výpočty statistik, pořadí a vyhodnocení skupin
    deleguje logiku na dedikovaný Results manager.
    """
    def __init__(self, setup: SetupWizard) -> None:
        # Základní identifikační a stavové atribudy turnaje
        self.results_manager = Results()
        self.name: str = setup.name
        self.tournament_format: str = setup.tournament_format
        self.raw_groups_data: dict = setup.groups
        self.stage: str = "groups"  # Aktualní fáze turnaje (začíná se ve skupinách)
        self.match_counter: int = 1 # počítadlo zápasů

        # Struktura větví turnaje pro správu pavouků
        self.branches: dict = {
            "main":None,  # Hlavní pavouk playoff
            "consolation":None, # útěcha
            "placement": {}  # dohrávkové zápasy o kontrétní umístění
        }

        #---- Pravidla turnaje načtená ze setupu ----
        self.group_match_format: str = setup.group_match_format
        self.advance_per_group: str = setup.advance_per_group
        self.group_elimination_action: str = setup.group_elimination_action
        self.playoff_match_format: str = setup.playoff_match_format
        self.playoff_elimination_action: str = setup.playoff_elimination_action



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
        self.processed_groups: set = set()

        self.main_playoff = Playoff(
            qualified_players=[],
            match_format=self.playoff_match_format,
            stage_name=self.stage,
            playoff_elimination_action=self.playoff_elimination_action
        )
        self.branches["main"] = self.main_playoff

        engine = SeedingEngine(tournament_format=self.tournament_format)

        self.main_playoff.generate_full_bracket_structure(groups=transformed_groups_dict,
                                                          start_rank=1,
                                                          end_rank=int(self.advance_per_group),
                                                          seeding_engine = engine)

        max_group_size = max(len(players) for players in transformed_groups_dict.values())
        start_rank = int(self.advance_per_group) + 1
        # PLAYOFF_B
        if self.group_elimination_action == "playoff_b" and start_rank <=max_group_size:
            self.branches["consolation"] = Playoff(
                qualified_players=[],
                match_format=self.playoff_match_format,
                stage_name="consolation",
                playoff_elimination_action=self.playoff_elimination_action
            )
            self.branches["consolation"].generate_full_bracket_structure(
                groups=transformed_groups_dict,
                seeding_engine=engine,
                start_rank=int(self.advance_per_group)+1,
                end_rank= max_group_size
            )
            print(f"DEBUG: Playoff B pro nepostupujícíc bylo vygenerováno.")

        #MINIGROUP
        elif self.group_elimination_action == "minigroup" and start_rank <= max_group_size:
            consolation_players = []
            for group_name in transformed_groups_dict:
                for rank in range(int(self.advance_per_group)+1, max_group_size+1):
                    consolation_players.append(f"{rank}{group_name}")

            self.branches["consolation"] = Group(
                groups_dict={"Útěcha": consolation_players},
                match_format=self.group_match_format,
                stage_name="consolation"
            )
            self.branches["consolation"].generate_matches(self)


    def get_next_match_id(self) -> int:
        """
        Vrátí aktuální ID pro nový zápas a posune počítadlo o 1 dál.
        Zajišťuje, že každý zápas v celém turnaji má své jedinečné ID.
        :return:
        """
        current_id = self.match_counter
        self.match_counter+=1
        return current_id

    def check_stage_progression(self) -> bool:
        """
        Průběžně kontroluje stav jednotlivých skupin.
        Pokud některá skupinaprávě dohrála a ještě nebyla zpracována,
        okamžitě vyhodnotí její výsledky a propíše postupující do playoff.
        """
        progres_made = False

        # Projedme všechny skupiny v názvech skupin.

        for group_name in self.group_stage.groups.keys():
            # Pokud skupina dohrála  a ještě není v seznamu zpracovaných
            if self.group_stage.are_all_matches_played(group_name=group_name) and group_name not in self.processed_groups:
                self.evaluate_single_group(group_name)
                self.processed_groups.add(group_name)
                progres_made = True

        # Celková kontrola, zda už jsou hoerá kromě prvního kola rovnou ptové všechny skupiny:

        if self.results_manager.are_groups_finished(self.group_stage):
            return True

        return progres_made

    def evaluate_single_group(self,group_name: str) -> None:
        """
        Vyhodnotí pouze kontrétní dohranou skupinu a propíše její postupující hráče do odpovídajících slotů v playoff.
        """
        # Získáme seřazené hráče v této kontrétní skupině pomocí result_managera
        ranked_players = self.group_stage.rank_players(group_name=group_name)

        # Určíme, kolik hráčů z této skupiny postupuje
        advance_count = int(self.advance_per_group)
        advancing_players = ranked_players[:advance_count]
        print(f"DEBUG: Skupina {group_name} dohrála! Postupující {[p.name for p in advancing_players]}")

        # Pošleme hráče do pavouka, ať si je zařadí
        if hasattr(self, "main_playoff") and self.main_playoff:
            self.main_playoff.update_slots_with_players(group_name=group_name,advancing_players=advancing_players,tournament=self)

        eliminated_players = ranked_players[advance_count:]

        if not eliminated_players:
            return

        consolation_branch = self.branches.get("consolation")
        if consolation_branch:
            if self.group_elimination_action == "playoff_b":
                consolation_branch.update_slots_with_players(
                    group_name=group_name,
                    advancing_players=eliminated_players,
                    tournament= self,
                    start_rank = advance_count
                )
                print(f"DEBUG: Nepostupující z {group_name} přidáni do playoff B")

            if self.group_elimination_action == "minigroup":
                matches_to_update = consolation_branch.group_matches.get("Útěcha",[])
                group_players_list = consolation_branch.groups.get("Útěcha", [])
                for i, real_player in enumerate(eliminated_players):
                    rank = advance_count + 1 + i
                    placeholder_name = f"{rank}{group_name}"

                    for match in matches_to_update:
                        if match.player_A == placeholder_name:
                            match.player_A = real_player
                        if match.player_B == placeholder_name:
                            match.player_B = real_player

                    for idx, player_item in enumerate(group_players_list):
                        if player_item == placeholder_name:
                            group_players_list[idx] = real_player

                print(f"DEBUG: Nepostupující z {group_name} přidání do minitabulky.")


    def get_groups_for_web(self,stage:str = "main")-> dict:
        """
        Vrátí slovník skupin a jejich aktuální pořadí ve formátu vhodném pro webové zobrazení.
        - stage: "main" pro základní skupiny, "consolation" pro útěchovou mini-skupinu.
        """
        # Určíme, ze kterého objektu budeme tahat data
        target_group = None

        if stage == "main":
            target_group = self.group_stage
        elif stage == "consolation":
            branch = self.branches.get("consolation")
            # Pro útěchu musíme ověřit, že je to opravdu instance Group
            if isinstance(branch, Group):
                target_group = branch
            else:
                return None

        if not target_group:
            return None

        # Skládáme slovník bezpečně s ohledem na placeholdery
        result = {}
        for name in target_group.groups.keys():
            web_players = []

            for p in target_group.rank_players(name):
                # Pokud je to pouze textový zástupce (např. "3A")
                if isinstance(p, str):
                    web_players.append({"name": p, "points": 0})
                # Pokud je to reálný hráč (objekt Player)
                else:
                    # Použijeme .get() pro bezpečné vytažení bodů
                    web_players.append({"name": p.name, "points": p.stats.get("points", 0)})

            result[name] = web_players

        return result

    def get_playoff_structure_for_web(self,branch_key: str="main") -> dict|None:
        """
        Vrátí strukturu kol a zápasů pro danou větev playoff (pro vykreslení na webu)
        -brach_key: Klíč větve (např. "main", "consolation")
        """
        playoff = self.branches.get(branch_key)
        return playoff.rounds if playoff else None

    def is_tournament_fully_finished(self) -> bool:
        """
        Zda je turnaj kompletně dohraný (včetně všech zápasů o umístění).
        Vrací True, pokud máme celkového vítěze a všechny dohrávkové zápasy jsou hotové
        """

        main_playoff = self.branches.get("main")
        # Pokud hlavní playoff nemá vítěze,turnaj neskončil
        if not (main_playoff and main_playoff.winner):
            return False

        # Projdeme všechny dohrávkové pavouky a zkontrolujeme, zda mají všechny zápasy hotové.
        if main_playoff and main_playoff.placement_rounds:
            for key, bracket_data in main_playoff.placement_rounds.items():
                for match in bracket_data.get("matches",[]):
                    if isinstance(match, Match) and not match.is_finished:
                        return False

        consolation = self.branches.get("consolation")
        # Pokud proměnná obsahuje instanci
        if consolation:
            # pokud se hraje Playoff B (instance Playoff)
            if isinstance(consolation, Playoff):
                # musí být vítěz
                if not consolation.winner:
                    return False
                # musí být dohrané dohrávky o umístění
                if consolation.placement_rounds:
                    for key, bracket_data in consolation.placement_rounds.items():
                        for match in bracket_data.get("matches", []):
                            if isinstance(match, Match) and not match.is_finished:
                                return False

            # hraná minitabulka o umístění
            elif isinstance(consolation,Group):
                # Projdeme všechny skupiny v rámci útěchy
                for group_name in consolation.groups.keys():
                    # Použijeme existující metodu pro kontrolu dohranosti skupin
                    if not consolation.are_all_matches_played(group_name=group_name):
                        return False

        return True

    def has_active_consolation(self)-> bool:
        """
        Vrací True, pokud větev útěchy existuje a reálně obsahuje data/hráče,
        jinak vrací False
        """
        consolation = self.branches.get("consolation")
        if not consolation:
            return False

        # Pokud je útěcha typu Group(minitabulka)
        if isinstance(consolation, Group):
            for group_name, players in consolation.groups.items():
                if players:
                    return True
            return False

        # Pokud je útěcha typu Playoff
        elif isinstance(consolation, Playoff):
            if consolation.rounds:
                return True
            return False

        return False

    def get_final_ranking(self) -> list[dict]:
        """
        Vrátí konečné počadí turnaje pomocí results_manageru.
        """
        return self.results_manager.compute_final_ranking(self.branches)