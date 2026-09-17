from app.models.models import Tournament as TournamentModel, Group as GroupModel, Match as MatchModel, Bracket as BracketModel, \
    Player as PlayerModel, ConsolationStats as ConsolationStatsModel, \
    GroupStats as GroupStatsModel, PlayoffStats as PlayoffStatsModel
from app.services.player import PlayerHelper
from app.services.groupmanager import GroupManager
from app.services.playoff import Playoff
from app.services.match import evaluate,toggle_match_progress, unlock_match


class WebManager:
    """
    Presenter vrstva: Zodpovídá za čtení dat z doménové logiky a jejich 
    transformaci do slovníků a formátů přichystaných pro HTML šablony.
    """

    def __init__(self, tournament_id: int):
        self.tournament_id = tournament_id
        self.tournament = TournamentModel.query.get_or_404(tournament_id)
        self.group_manager = GroupManager(tournament_id, self.tournament.group_match_format)

    def get_groups_page_data(self) -> dict:
        """Připraví data pro stránku se základními skupinami (groups.html)."""
        group_data = {}
        groups = GroupModel.query.filter_by(tournament_id=self.tournament_id, is_consolation=False).order_by(
            GroupModel.name.asc()).all()

        for group in groups:
            ranked_players = self.group_manager.rank_players(group.id, "Group")
            group_data[group.name.replace("Skupina ", "")] = {
                "players": self._format_players(ranked_players, "Group"),
                "matches": self._format_matches(group.matches)
            }
        return group_data

    def process_match_action(self, form_data, is_playoff=False, is_consolation=False):
        """Univerzální zpracování zápasových akcí (toggle, unlock, submit_result)."""
        match_id = int(form_data.get("match_id", 0))
        action = form_data.get("action")

        if not match_id or not action:
            return

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            # Vyhodnocení samotného zápasu (sety)
            evaluate(
                match_id=match_id,
                player_a_games=form_data.getlist("game_a[]"),
                player_b_games=form_data.getlist("game_b[]")
            )

            # Dokončení podle typu turnaje (skupina vs playoff)
            if is_playoff:
                self.handle_playoff_completion(is_consolation=is_consolation)
            else:
                self.group_manager.handle_match_completion(match_id, self.tournament)

    def get_minigroup_page_data(self) -> dict:
        """Připraví data pro minitabulku útěchy (consolation_minigroup.html)."""
        group_data = {}
        cons_bracket = BracketModel.query.filter_by(
            tournament_id=self.tournament_id,
            is_consolation=True,
            bracket_type="round_robin"
        ).first()

        if cons_bracket:
            # 1. Vytáhneme reálné zápasy minitabulky z DB
            matches = MatchModel.query.filter_by(bracket_id=cons_bracket.id).all()

            # 2. Sesbíráme hráče, kteří už v minitabulce mají zápasy, NEBO už mají group_seed odpovídající vyřazeným
            match_player_ids = {m.player_a_id for m in matches if m.player_a_id} | {m.player_b_id for m in matches if
                                                                                    m.player_b_id}

            # Navíc se podíváme do tree_data, jaké seedy (např "3A", "3B") tato minitabulka vůbec očekává
            tree_data = cons_bracket.tree_data or {}
            expected_seeds = set()
            for slot_a, slot_b in tree_data.get("matches", []):
                if isinstance(slot_a, str): expected_seeds.add(slot_a)
                if isinstance(slot_b, str): expected_seeds.add(slot_b)

            # Najdeme hráče, kteří odpovídají těmto seedům a už mají přiřazené ID / dohráli skupinu
            seeded_players = PlayerModel.query.filter(
                PlayerModel.tournament_id == self.tournament_id,
                PlayerModel.group_seed.in_(expected_seeds)
            ).all()

            all_player_ids = match_player_ids | {p.id for p in seeded_players}
            players = PlayerModel.query.filter(PlayerModel.id.in_(all_player_ids)).all()

            all_player_ids = match_player_ids | {p.id for p in seeded_players}
            players = PlayerModel.query.filter(PlayerModel.id.in_(all_player_ids)).all()

            #Použití get_sorting_stats pro správnou fázi turnaje
            ranked = sorted(
                players,
                key=lambda p: PlayerHelper.get_sorting_stats(p.id, "minigroup"),
                reverse=True
            )

            group_data[cons_bracket.name] = {
                "players": self._format_players(ranked, "minigroup"),
                "matches": self._format_matches(matches)
            }

        return group_data

    def get_playoff_page_data(self, is_consolation: bool = False) -> dict:
        """Připraví data pro hlavní nebo útěchový pavouk."""
        bracket, rank_offset, stage_name = self._get_playoff_bracket_info(is_consolation)
        p_data = None
        if bracket:
            engine = Playoff(
                tournament_id=self.tournament_id,
                match_format=self.tournament.playoff_match_format,
                stage_name=stage_name,
                playoff_elimination_action=self.tournament.playoff_elimination_action,
                bracket_id=bracket.id,
                rank_offset=rank_offset
            )
            p_data = engine.get_ui_data()
        return p_data

    def handle_playoff_completion(self, is_consolation: bool = False) -> None:
        """Spustí playoff motor pro posun hráčů a zápis výsledků."""
        bracket, rank_offset, stage_name = self._get_playoff_bracket_info(is_consolation)
        if bracket:
            engine = Playoff(
                tournament_id=self.tournament_id,
                match_format=self.tournament.playoff_match_format,
                stage_name=stage_name,
                playoff_elimination_action=self.tournament.playoff_elimination_action,
                bracket_id=bracket.id,
                rank_offset=rank_offset
            )
            engine.check_and_proceed()
            engine.save_to_db()

    def _get_playoff_bracket_info(self, is_consolation: bool):
        """Pomocná metoda pro zjištění parametrů playoff bracketu."""
        if is_consolation:
            bracket = BracketModel.query.filter_by(
                tournament_id=self.tournament_id,
                is_consolation=True,
                bracket_type="elimination"
            ).first()
            main_groups_count = GroupModel.query.filter_by(tournament_id=self.tournament_id,
                                                           is_consolation=False).count()
            rank_offset = self.tournament.advance_per_group * main_groups_count
            stage_name = "consolation"
        else:
            bracket = BracketModel.query.filter_by(
                tournament_id=self.tournament_id,
                name="Hlavní Playoff"
            ).first()
            rank_offset = 0
            stage_name = "main"
        return bracket, rank_offset, stage_name

    def get_results_data(self) -> list:
        """Připraví seřazená data s konečným pořadím hráčů pro výsledkovou stránku."""
        players = PlayerModel.query.filter_by(tournament_id=self.tournament_id).all()
        results_data = []

        for player in players:
            p_stats = PlayoffStatsModel.query.filter_by(player_id=player.id).first()
            c_stats = ConsolationStatsModel.query.filter_by(player_id=player.id).first()

            rank = None
            if p_stats and p_stats.final_rank is not None:
                rank = p_stats.final_rank
            elif c_stats and c_stats.final_rank is not None:
                rank = c_stats.final_rank

            if rank is not None:
                results_data.append((player, rank))

        # Seřadíme podle získaného pořadí vzestupně (1., 2., 3. místo...)
        results_data.sort(key=lambda x: x[1])
        return results_data

    # ==========================================
    # PRIVÁTNÍ POMOCNÉ METODY PRO FORMÁTOVÁNÍ
    # ==========================================

    @staticmethod
    def _format_players(players: list, stage_name: str) -> list:
        if not players:
            return []

        player_ids = [p.id for p in players]

        # Rozhodneme se podle fáze, do které tabulky se podíváme
        if stage_name == "Group":
            all_stats = GroupStatsModel.query.filter(GroupStatsModel.player_id.in_(player_ids)).all()
        else:
            all_stats = ConsolationStatsModel.query.filter(ConsolationStatsModel.player_id.in_(player_ids)).all()

        stats_map = {s.player_id: s for s in all_stats}

        ui_data = []
        for p in players:
            stats = stats_map.get(p.id)
            if stats:
                games_win = getattr(stats, 'games_win', 0)
                games_lost = getattr(stats, 'games_lost', 0)
                balls_diff = stats.balls_win - stats.balls_lost if hasattr(stats, 'balls_win') else 0
                points = getattr(stats, 'points', 0)
            else:
                games_win, games_lost, balls_diff, points = 0, 0, 0, 0

            ui_data.append({
                "name": p.name,
                "games_win": games_win,
                "games_lost": games_lost,
                "balls_diff": balls_diff,
                "points": points
            })
        return ui_data

    @staticmethod
    def _format_matches(matches: list) -> list:
        ui_data = []
        for m in sorted(matches, key=lambda x: x.id):
            played_sets = []
            if hasattr(m, 'sets') and m.sets:
                # Seřadíme je podle čísla setu, aby šly popořadě (1. set, 2. set...)
                sorted_sets = sorted(m.sets, key=lambda s: s.set_number)
                for s in sorted_sets:
                    played_sets.append((s.score_a, s.score_b))

            # Zjistíme jméno vítěze zápasu (pokud má nastavený winner_id)
            winner_name = None
            if m.winner_id:
                if m.winner_id == m.player_a_id and m.player_a:
                    winner_name = m.player_a.name
                elif m.winner_id == m.player_b_id and m.player_b:
                    winner_name = m.player_b.name

            ui_data.append({
                "match_id": m.id,
                "player_a_name": m.player_a.name if m.player_a else "TBD",
                "player_b_name": m.player_b.name if m.player_b else "TBD",
                "is_finished": m.is_finished,
                "is_in_progress": getattr(m, "is_in_progress", False),
                "match_format": m.match_format,
                "played_sets": played_sets,
                "winner_name": winner_name
            })
        return ui_data

