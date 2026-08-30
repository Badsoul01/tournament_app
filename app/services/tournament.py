from app.services.setupwizard import SetupWizard
from app.models.models import db, Tournament as TournamentModel, Group as GroupModel, Player as PlayerModel, \
    Match as MatchModel, Bracket as BracketModel
from app.services.groupmanager import GroupManager
from app.services.seedingengine import SeedingEngine
from app.services.playoff import Playoff

class Tournament:
    """
    Třída zodpovědná za celkovou orchestraci turnaje a zápis do databáze.
    """

    def __init__(self, setup: SetupWizard) -> None:
        is_consolation = setup.group_elimination_action in ["playoff_b", "minigroup"]

        db_tournament = TournamentModel(
            name = setup.name,
            advance_per_group=setup.advance_per_group,
            group_elimination_action=setup.group_elimination_action,
            has_consolation=is_consolation,
            playoff_elimination_action=setup.playoff_elimination_action,
            group_match_format =setup.group_match_format,
            playoff_match_format = setup.playoff_match_format
        )
        db.session.add(db_tournament)
        db.session.commit()

        self.id = db_tournament.id
        self._build_database_structure(raw_groups=setup.groups)
        group_manager = GroupManager(tournament_id=self.id, match_format=setup.group_match_format)
        group_manager.generate_group_matches()

        self.branches: dict = {
            "main": None,  # Hlavní pavouk playoff
            "consolation": None,  # útěcha
        }

        self._build_playoff(setup=setup)


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

    def _build_playoff(self, setup) -> None:
        """Sestaví struktury z databázea uloží nové Brackets v JSON formátu."""

        # 1. Vytáhneme skupiny a jejich hráče z databáze pro tento turnaj
        db_groups = GroupModel.query.filter_by(tournament_id=self.id, is_consolation=False).all()

        # 2. Sestavíme slovník { "A": [hráč1, hráč2, ...], "B": [...] }
        groups_dict = {g.name.replace("Skupina ", "").strip(): list(g.players) for g in db_groups}


        # 3. Inicializujeme Playoff a necháme ho vygenerovat strukturu v paměti
        engine = SeedingEngine()

        main_playoff = Playoff(
            tournament_id=self.id,
            match_format=int(setup.playoff_match_format),
            stage_name="main",
            playoff_elimination_action=setup.playoff_elimination_action
        )

        main_playoff.generate_full_bracket_structure(
            groups=groups_dict,
            seeding_engine=engine,
            start_rank=1,
            end_rank=int(setup.advance_per_group)
        )

        db_main_bracket = BracketModel(
            tournament_id=self.id,
            name="Hlavní Playoff",
            bracket_type="elimination",
            is_consolation=False,
            tree_data={"rounds": main_playoff.rounds, "placement_rounds": getattr(main_playoff, "placement_rounds", {})}
        )
        db.session.add(db_main_bracket)

        self.branches["main"] = main_playoff


        if setup.group_elimination_action in ["playoff_b", "minigroup"]:
            has_eliminated_players = any(len(players) > int(setup.advance_per_group) for players in groups_dict.values())

            if has_eliminated_players:
                # Pro playoff_b vytvoříme in-memory strukturu pavouka útěchy
                if setup.group_elimination_action == "playoff_b":
                    advancing_total = int(setup.advance_per_group) * len(groups_dict)
                    cons_playoff = Playoff(
                        tournament_id=self.id,
                        match_format=int(setup.playoff_match_format),
                        stage_name="consolation",
                        playoff_elimination_action=setup.playoff_elimination_action,
                        rank_offset=advancing_total
                    )
                    # Zde se pak struktura naplní z pozic od advance_per_group + 1 dál
                    cons_playoff.generate_full_bracket_structure(
                        groups=groups_dict,
                        seeding_engine=engine,
                        start_rank=int(setup.advance_per_group) + 1,
                        end_rank=max(len(p) for p in groups_dict.values())
                    )

                    db_cons_bracket = BracketModel(
                        tournament_id=self.id,
                        name="Útěcha (Playoff B)",
                        bracket_type="elimination",
                        is_consolation=True,
                        tree_data={"rounds": cons_playoff.rounds, "placement_rounds": getattr(cons_playoff, "placement_rounds", {})}
                    )
                    db.session.add(db_cons_bracket)

                    self.branches["consolation"] = cons_playoff

                # Pro minitabulku (minigroup) si připravíme dynamické sloty
                elif setup.group_elimination_action == "minigroup":
                    # 1. Vypočítáme budoucí značky (seedy) vyřazených hráčů (např. "3A", "3B", "4B")
                    eliminated_seeds = []
                    advancing = int(setup.advance_per_group)
                    for group_name, players in groups_dict.items():
                        if len(players) > advancing:
                            for i in range(advancing, len(players)):
                                eliminated_seeds.append(f"{i + 1}{group_name}")

                    # 2. Vygenerujeme kruhový systém pouze pro tyto textové značky (n-tice)
                    minigroup_slots = []
                    match_players = list(eliminated_seeds)
                    if len(match_players) % 2 != 0:
                        match_players.append("BYE")

                    n = len(match_players)
                    for r in range(n - 1):
                        for i in range(n // 2):
                            p_a = match_players[i]
                            p_b = match_players[n - 1 - i]
                            if p_a != "BYE" and p_b != "BYE":
                                minigroup_slots.append((p_a, p_b))
                        match_players = [match_players[0]] + [match_players[-1]] + match_players[1:-1]

                    db_cons_bracket = BracketModel(
                        tournament_id=self.id,
                        name="Útěcha-Minitabulka",
                        bracket_type="round_robin",
                        is_consolation=True,
                        tree_data={"matches":minigroup_slots}
                    )
                    db.session.add(db_cons_bracket)

                    # 4. Uložíme si to do paměti pavouka
                    self.branches["consolation"] = {
                        "type": "minigroup",
                        "group_id": db_cons_bracket.id,
                        "matches": minigroup_slots
                    }
            else:
                # Žádní hráči na vyřazení nezbyli (např. všichni postupují do hlavního pavouka)
                # Takže v DB natvrdo vypneme konzoli, aby zmizela z menu
                db_tournament = TournamentModel.query.get(self.id)
                if db_tournament:
                    db_tournament.has_consolation = False
                    db.session.commit()

        db.session.commit()

    def is_tournament_fully_finished(self):
        """Zkontroluje, zda jsou všechny zápasy v turnaji (skupiny i playoff) dohrané."""

        # Pokusíme se najít alespoň jeden zápas tohoto turnaje, který NENÍ dohraný
        unfinished_match = MatchModel.query.filter_by(
            tournament_id=self.id,
            is_finished=False
        ).first()

        # Pokud se žádný nedohraný nenajde (unfinished_match je None), turnaj je hotový
        return unfinished_match is None

    @staticmethod
    def finish_existing_tournament(tournament_id: int) -> bool:
        db_tournament = TournamentModel.query.get(tournament_id)
        if not db_tournament or db_tournament.is_finished:
            return False

        # Zkontrolujeme, zda jsou všechny zápasy dohrané
        # (vytvoříme dočasnou instanci orchestrátoru nebo ověříme přes dotaz na DB)
        unfinished_match = MatchModel.query.filter_by(
            tournament_id=tournament_id,
            is_finished=False
        ).first()

        if unfinished_match is not None:
            # Turnaj ještě není dohraný, zamknutí zamítneme
            return False

        db_tournament.is_finished = True

        from run.models.models import PlayerStats as PlayerStatsModel, GlobalPlayer
        results_data = db.session.query(PlayerModel, PlayerStatsModel.final_rank) \
            .join(PlayerStatsModel, PlayerModel.id == PlayerStatsModel.player_id) \
            .filter(PlayerModel.tournament_id == tournament_id) \
            .filter(PlayerStatsModel.final_rank.isnot(None)) \
            .all()

        for player, rank in results_data:
            global_player = GlobalPlayer.query.filter_by(name=player.name).first()
            if not global_player:
                global_player = GlobalPlayer(name=player.name)
                db.session.add(global_player)
                db.session.flush()

            player.global_player_id = global_player.id
            global_player.tournaments_played = (global_player.tournaments_played or 0) + 1
            global_player.sum_of_ranks = (global_player.sum_of_ranks or 0) + rank
            global_player.last_rank = rank
            global_player.last_tournament_date = db_tournament.date

        db.session.commit()
        return True