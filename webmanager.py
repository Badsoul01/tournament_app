from models import Tournament as TournamentModel, Group as GroupModel, Match as MatchModel, Bracket as BracketModel, \
    Player as PlayerModel
from player import PlayerHelper
from groupmanager import GroupManager
from playoff import Playoff


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

    def get_minigroup_page_data(self) -> dict:
        """Připraví data pro minitabulku útěchy (consolation_minigroup.html)."""
        group_data = {}
        cons_bracket = BracketModel.query.filter_by(
            tournament_id=self.tournament_id,
            is_consolation=True,
            bracket_type="round_robin"
        ).first()

        if cons_bracket:
            matches = MatchModel.query.filter_by(bracket_id=cons_bracket.id).all()
            player_ids = {m.player_a_id for m in matches if m.player_a_id} | {m.player_b_id for m in matches if
                                                                              m.player_b_id}
            players = PlayerModel.query.filter(PlayerModel.id.in_(player_ids)).all()

            ranked = sorted(
                players,
                key=lambda p: (
                    PlayerHelper.get_or_create_stats(p.id, "minigroup").points,
                    PlayerHelper.difference_of_score(p.id, "minigroup")["Balls"]
                ),
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

    # ==========================================
    # PRIVÁTNÍ POMOCNÉ METODY PRO FORMÁTOVÁNÍ
    # ==========================================
    @staticmethod
    def _format_players(players: list, stage_name: str) -> list:
        ui_data = []
        for p in players:
            stats = PlayerHelper.get_or_create_stats(p.id, stage_name)
            diff = PlayerHelper.difference_of_score(p.id, stage_name)
            ui_data.append({
                "name": p.name,
                "games_win": stats.games_win,
                "games_lost": stats.games_lost,
                "balls_diff": diff["Balls"],
                "points": stats.points
            })
        return ui_data

    @staticmethod
    def _format_matches(matches: list) -> list:
        ui_data = []
        for m in sorted(matches, key=lambda x: x.id):
            played_sets = []
            if m.sets_data:
                for s in m.sets_data.split(","):
                    if ":" in s:
                        a, b = s.split(":")
                        played_sets.append((int(a), int(b)))
            ui_data.append({
                "match_id": m.id,
                "player_a_name": m.player_a.name if m.player_a else "TBD",
                "player_b_name": m.player_b.name if m.player_b else "TBD",
                "is_finished": m.is_finished,
                "is_in_progress": getattr(m, "is_in_progress", False),
                "match_format": m.match_format,
                "played_sets": played_sets
            })
        return ui_data