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
        self.stage: str = "groups"  # Aktualní fáze turnaje (začíná se ve skupinách)
        self.match_counter: int = 1 # počítadlo zápasů

        # Struktura větví turnaje pro správu pavouků
        self.branches: dict = {
            "main":None,  # Hlavní pavouk playoff
            "consolation":None, # útěcha
        }

        #---- Pravidla turnaje načtená ze setupu ----
        self.group_match_format: str = setup.group_match_format
        self.advance_per_group: str = setup.advance_per_group
        self.group_elimination_action: str = setup.group_elimination_action
        self.playoff_match_format: str = setup.playoff_match_format
        self.playoff_elimination_action: str = setup.playoff_elimination_action

        # Fyzická stavba turnaje (delegováno na privátní metody)
        self._build_group_stage(raw_groups=setup.groups)
        self._build_main_playoff()
        self._build_consolation()

    def _build_group_stage(self,raw_groups: dict) -> None:
        """Svěří tvorbu skupin a instanci hráčů přímo třídě Group."""
        self.group_stage = Group.create_from_raw_data(
            raw_groups_dict=raw_groups,
            match_format=self.group_match_format,
            stage_name="Group"
        )
        self.group_stage.generate_matches(self)
        self.processed_groups: set = set()

    def _build_main_playoff(self) -> None:
        """Připraví hlavní Playoff a zavoláý seedingEngine pro prvnotní pavouk"""
        self.main_playoff = Playoff(
            qualified_players=[],
            match_format=self.playoff_match_format,
            stage_name=self.stage,
            playoff_elimination_action=self.playoff_elimination_action
        )
        self.branches["main"] = self.main_playoff

        engine = SeedingEngine(tournament_format=self.tournament_format)
        self.main_playoff.generate_full_bracket_structure(
            groups=self.group_stage.groups,
            seeding_engine=engine,
            start_rank=1,
            end_rank=int(self.advance_per_group)
        )

    def _build_consolation(self) -> None:
        """Dynamicky vygeneruje větev pro nepostupující ze skupin, pokud je aktivní"""
        max_group_size = max(len(players) for players in self.group_stage.groups.values())
        start_rank = int(self.advance_per_group) + 1

        # PLAYOFF B
        if self.group_elimination_action == "playoff_b" and start_rank <= max_group_size:
            engine = SeedingEngine(tournament_format=self.tournament_format)
            self.branches["consolation"] = Playoff(
                qualified_players=[],
                match_format=self.playoff_match_format,
                stage_name="consolation",
                playoff_elimination_action=self.playoff_elimination_action
            )
            self.branches["consolation"].generate_full_bracket_structure(
                groups=self.group_stage.groups,
                seeding_engine=engine,
                start_rank=start_rank,
                end_rank=max_group_size
            )
            print(f"DEBUG: Playoff B pro nepostupující bylo vygenerováno.")

        # MINIGROUP
        elif self.group_elimination_action == "minigroup" and start_rank <= max_group_size:
            consolation_players = []
            for group_name in self.group_stage.groups.keys():
                for rank in range(start_rank,max_group_size + 1):
                    consolation_players.append(f"{rank}{group_name}")

            self.branches["consolation"] = Group(
                groups_dict={"Útěcha":consolation_players},
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
                for i, real_player in enumerate(eliminated_players):
                    rank = advance_count + 1 + i
                    placeholder_name = f"{rank}{group_name}"

                    # elegantní  delegace na třídu Group
                    consolation_branch.replace_placeholder(
                        group_name="Útěcha",
                        placeholder= placeholder_name,
                        real_player= real_player
                    )
                print(f"DEBUG: Nepostupující z {group_name} přidání do minitabulky.")

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
        if hasattr(main_playoff,"placement_rounds") and main_playoff.placement_rounds:
            for bracket_data in main_playoff.placement_rounds.values():
                for match in bracket_data.get("matches", []):
                    if hasattr(match,"is_finished") and not match.is_finished:
                        return False

        consolation = self.branches.get("consolation")
        # Pokud proměnná obsahuje instanci
        if consolation:
            # pokud se hraje Playoff B (instance Playoff)
            if hasattr(consolation, "rounds"):
                # musí být vítěz
                if not consolation.winner:
                    return False
                # musí být dohrané dohrávky o umístění
                if hasattr(consolation, "placement_rounds") and consolation.placement_rounds:
                    for bracket_data in consolation.placement_rounds.values():
                        for match in bracket_data.get("matches", []):
                            if hasattr(match,"is_finished") and not match.is_finished:
                                return False

            # hraná minitabulka o umístění
            elif hasattr(consolation,"groups"):
                # Projdeme všechny skupiny v rámci útěchy
                for group_name in consolation.groups.keys():
                    # Použijeme existující metodu pro kontrolu dohranosti skupin
                    if not consolation.are_all_matches_played(group_name=group_name):
                        return False

        return True