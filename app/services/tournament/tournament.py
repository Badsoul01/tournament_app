from app.services.tournament.setupwizard import SetupWizard
from app.models.models import db, Tournament as TournamentModel, Group as GroupModel, Player as PlayerModel, \
    Match as MatchModel, Bracket as BracketModel,GlobalPlayer as GlobalPlayerModel, PlayoffStats as PlayoffStatsModel, \
    ConsolationStats as ConsolationStatsModel
from app.services.tournament.groupmanager import GroupManager
from app.services.tournament.seedingengine import SeedingEngine
from app.services.tournament.playoff import Playoff
from flask import session
from datetime import datetime


class Tournament:
    """
    Třída zodpovědná za celkovou orchestraci turnaje a zápis do databáze.
    """

    def __init__(self, setup: SetupWizard) -> None:

        # =========================================================
        # POČET POSTUPUJÍCÍCH
        # =========================================================

        # Jedna skupina používá vlastní nastavení počtu postupujících.
        if setup.is_single_group:
            advancing_count = setup.single_group_playoff_count
        else:
            advancing_count = setup.advance_per_group

        has_playoff_flag = advancing_count > 0

        # =========================================================
        # TURNAJ
        # =========================================================

        db_tournament = TournamentModel(
            name=setup.name,

            date=datetime.strptime(
                setup.date,
                "%Y-%m-%d"
            ),

            location=setup.location or None,
            tournament_format=setup.tournament_format,
            include_in_global_stats=setup.include_in_global_stats,
            group_match_format=setup.group_match_format,
            playoff_match_format=setup.playoff_match_format,
            advance_per_group=advancing_count,
            group_elimination_action=setup.group_elimination_action,
            playoff_elimination_action=setup.playoff_elimination_action,
            total_players=setup.total_tournament_players,
            total_players_in_playoff=setup.total_players_advance_to_playoff,
            has_playoff=has_playoff_flag,
            has_consolation=False,

            consolation_format=setup.group_elimination_action
        )

        # =========================================================
        # ORGANIZÁTOR
        # =========================================================

        if 'organizer_id' in session:
            db_tournament.organizer_id = session['organizer_id']

        db.session.add(db_tournament)
        db.session.commit()

        self.id = db_tournament.id

        # =========================================================
        # HOSTOVSKÝ TURNAJ
        # =========================================================

        if 'organizer_id' not in session:
            if 'guest_tournaments' not in session:
                session['guest_tournaments'] = []

            if self.id not in session['guest_tournaments']:
                session['guest_tournaments'].append(self.id)
                session.modified = True

        # =========================================================
        # SKUPINY A HRÁČI
        # =========================================================

        self._build_database_structure(
            raw_groups=setup.groups
        )

        group_manager = GroupManager(
            tournament_id=self.id,
            match_format=setup.group_match_format
        )

        group_manager.generate_group_matches()

        # =========================================================
        # VĚTVE TURNAJE
        # =========================================================

        self.branches: dict = {
            "main": None,
            "consolation": None,
        }

        # =========================================================
        # PLAYOFF
        # =========================================================

        self._build_playoff(
            setup=setup,
            advancing_count=advancing_count
        )


    def _build_database_structure(self, raw_groups: dict) -> None:
        """Vezme surová data ze setupu a uloží skupiny a hráče do databáze hromadně."""

        for group_letter, player_names in raw_groups.items():
            # 1. Vytvoříme záznam skupiny v paměti session (bez commitu)
            db_group = GroupModel(
                name=f"Skupina {group_letter}",
                is_consolation=False,
                tournament_id=self.id
            )
            db.session.add(db_group)
            # Flush zajistí, že databáze vygeneruje ID pro db_group,
            # abychom ho mohli hned přiřadit hráčům, ale nezatěžuje to sítě finálním commitem
            db.session.flush()

            # 2. Přidáme hráče této skupiny do paměti session
            for name in player_names:
                db_player = PlayerModel(
                    name=name,
                    tournament_id=self.id,
                    group_id=db_group.id
                )
                db.session.add(db_player)

        # 3. Jeden jediný hromadný commit pro všechny skupiny i hráče naráz
        db.session.commit()

    def _build_playoff(
            self,
            setup: SetupWizard,
            advancing_count: int
    ) -> None:

        """
        Vytvoří hlavní playoff a případnou útěchu
        pro turnaj se skupinovou fází.
        """

        # =========================================================
        # DATA SKUPIN
        # =========================================================

        db_groups = GroupModel.query.filter_by(
            tournament_id=self.id,
            is_consolation=False
        ).all()

        groups_dict = {
            group.name.replace("Skupina ", "").strip():
                list(group.players)
            for group in db_groups
        }

        engine = SeedingEngine()

        # =========================================================
        # 1. HLAVNÍ PLAYOFF
        # =========================================================

        if advancing_count > 0:

            main_playoff = Playoff(
                tournament_id=self.id,
                match_format=setup.playoff_match_format,
                stage_name="main",
                playoff_elimination_action=setup.playoff_elimination_action
            )

            main_playoff.generate_full_bracket_structure(
                groups=groups_dict,
                seeding_engine=engine,
                start_rank=1,
                end_rank=advancing_count
            )

            db_main_bracket = BracketModel(
                tournament_id=self.id,
                name="Hlavní Playoff",
                bracket_type="elimination",
                is_consolation=False,
                tree_data={
                    "rounds": main_playoff.rounds,
                    "placement_rounds": getattr(
                        main_playoff,
                        "placement_rounds",
                        {}
                    )
                }
            )

            db.session.add(db_main_bracket)

            self.branches["main"] = main_playoff

        else:
            self.branches["main"] = None

        # =========================================================
        # 2. ÚTĚCHA
        # =========================================================

        if setup.group_elimination_action in [
            "playoff_b",
            "minigroup"
        ]:

            has_eliminated_players = any(
                len(players) > advancing_count
                for players in groups_dict.values()
            )

            if has_eliminated_players:

                # =================================================
                # PLAYOFF B
                # =================================================

                if setup.group_elimination_action == "playoff_b":

                    advancing_total = (
                        setup.total_players_advance_to_playoff
                    )

                    cons_playoff = Playoff(
                        tournament_id=self.id,
                        match_format=setup.playoff_match_format,
                        stage_name="consolation",
                        playoff_elimination_action=(
                            setup.playoff_elimination_action
                        ),
                        rank_offset=advancing_total
                    )

                    cons_playoff.generate_full_bracket_structure(
                        groups=groups_dict,
                        seeding_engine=engine,
                        start_rank=advancing_count + 1,
                        end_rank=max(
                            len(players)
                            for players in groups_dict.values()
                        )
                    )

                    db_cons_bracket = BracketModel(
                        tournament_id=self.id,
                        name="Útěcha (Playoff B)",
                        bracket_type="elimination",
                        is_consolation=True,
                        tree_data={
                            "rounds": cons_playoff.rounds,
                            "placement_rounds": getattr(
                                cons_playoff,
                                "placement_rounds",
                                {}
                            )
                        }
                    )

                    db.session.add(db_cons_bracket)

                    self.branches["consolation"] = cons_playoff

                # =================================================
                # MINI-SKUPINA
                # =================================================

                elif setup.group_elimination_action == "minigroup":

                    eliminated_seeds = []

                    for group_name, players in groups_dict.items():

                        if len(players) > advancing_count:

                            for index in range(
                                    advancing_count,
                                    len(players)
                            ):
                                eliminated_seeds.append(
                                    f"{index + 1}{group_name}"
                                )

                    minigroup_slots = []

                    match_players = list(eliminated_seeds)

                    if len(match_players) % 2 != 0:
                        match_players.append("BYE")

                    number_of_players = len(match_players)

                    for _ in range(number_of_players - 1):

                        for index in range(
                                number_of_players // 2
                        ):
                            player_a = match_players[index]
                            player_b = match_players[
                                number_of_players - 1 - index
                                ]

                            if (
                                    player_a != "BYE"
                                    and player_b != "BYE"
                            ):
                                minigroup_slots.append(
                                    (player_a, player_b)
                                )

                        match_players = (
                                [match_players[0]]
                                + [match_players[-1]]
                                + match_players[1:-1]
                        )

                    db_cons_bracket = BracketModel(
                        tournament_id=self.id,
                        name="Útěcha-Minitabulka",
                        bracket_type="round_robin",
                        is_consolation=True,
                        tree_data={
                            "matches": minigroup_slots
                        }
                    )

                    db.session.add(db_cons_bracket)

                    self.branches["consolation"] = {
                        "type": "minigroup",
                        "group_id": db_cons_bracket.id,
                        "matches": minigroup_slots
                    }

                # =================================================
                # ÚTĚCHA BYLA VYTVOŘENA
                # =================================================

                db_tournament = TournamentModel.query.get(
                    self.id
                )

                if db_tournament:
                    db_tournament.has_consolation = True

        db.session.commit()

    def is_tournament_fully_finished(self):
        """Zkontroluje, zda jsou všechny reálné zápasy v turnaji dohrané (ignoruje BYE vs BYE)."""

        # Vytáhneme všechny nedohrané zápasy turnaje
        unfinished_matches = MatchModel.query.filter_by(
            tournament_id=self.id,
            is_finished=False
        ).all()

        # Projdeme je a podíváme se, jestli je mezi nimi nějaký reálný zápas k dohrání
        for match in unfinished_matches:
            # Zjistíme, jestli má zápas oba hráče (pokud by se pracovalo s ID, nebo názvy)
            # Zápas je "reálný" a vyžaduje dohrání, pokud má oba hráče a ani jeden není BYE / prázdný
            has_player_a = match.player_a_id is not None
            has_player_b = match.player_b_id is not None

            # Pokud má oba hráče, je to platný zápas, který se musí dohrát
            if has_player_a and has_player_b:
                return False

        # Pokud zbývají jen prázdné/BYE zápasy, turnaj se považuje za dohraný
        return True

    @staticmethod
    def finish_existing_tournament(tournament_id: int) -> bool:
        db_tournament = TournamentModel.query.get(tournament_id)
        if not db_tournament or db_tournament.is_finished:
            return False

        # Zkontrolujeme, zda jsou všechny zápasy dohrané
        unfinished_match = MatchModel.query.filter_by(
            tournament_id=tournament_id,
            is_finished=False
        ).first()

        if unfinished_match is not None:
            print("Turnaj nemá dohráno.")
            return False

        db_tournament.is_finished = True

        # Načteme všechny hráče daného turnaje
        players = PlayerModel.query.filter_by(tournament_id=tournament_id).all()

        for player in players:
            global_player = GlobalPlayerModel.query.filter_by(name=player.name.strip().title()).first()
            if not global_player:
                global_player = GlobalPlayerModel(name=player.name.strip().title())
                db.session.add(global_player)
                db.session.flush()

            player.global_player_id = global_player.id

            # Zjistíme, jestli má hráč statistiky v hlavním pavouku nebo v útěše
            playoff_stats = PlayoffStatsModel.query.filter_by(player_id=player.id).first()
            consolation_stats = ConsolationStatsModel.query.filter_by(player_id=player.id).first()

            # Upřednostníme hlavní pavouk, jinak vezmeme útěchu
            active_stats = None
            if playoff_stats and playoff_stats.final_rank is not None:
                active_stats = playoff_stats
            elif consolation_stats and consolation_stats.final_rank is not None:
                active_stats = consolation_stats

            points_gained = getattr(active_stats, 'points_gained', 0) if active_stats else 0
            final_rank = getattr(active_stats, 'final_rank', None) if active_stats else None

            global_player.last_points_gained = points_gained or 0

            # Uložení statistik účasti do globálního žebříčku
            if final_rank:
                global_player.tournaments_played = (global_player.tournaments_played or 0) + 1
                global_player.sum_of_ranks = (global_player.sum_of_ranks or 0) + final_rank
                global_player.last_rank = final_rank
                global_player.last_tournament_date = db_tournament.date

            # Zápis statistik zápasů
            player_matches = MatchModel.query.filter(
                (MatchModel.player_a_id == player.id) | (MatchModel.player_b_id == player.id),
                MatchModel.is_finished == True
            ).all()

            for match in player_matches:
                global_player.matches_played = (global_player.matches_played or 0) + 1

                if match.winner_id == player.id:
                    global_player.matches_won = (global_player.matches_won or 0) + 1
                elif match.winner_id is None and match.player_a_id and match.player_b_id:
                    global_player.matches_drawn = (global_player.matches_drawn or 0) + 1
                elif match.winner_id is not None:
                    global_player.matches_lost = (global_player.matches_lost or 0) + 1

        #  Zápis celkového vítěze turnaje
        winner_stat = PlayoffStatsModel.query.join(PlayerModel).filter(
            PlayerModel.tournament_id == tournament_id,
            PlayoffStatsModel.final_rank == 1
        ).first()

        if winner_stat:
            db_tournament.winner_id = winner_stat.player_id
            print(f"DEBUG: Vítězem turnaje {tournament_id} byl zapsán hráč s ID {winner_stat.player_id}")


        db.session.commit()
        return True