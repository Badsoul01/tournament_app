from app.models.models import (
    Tournament as TournamentModel,
    Match as MatchModel, db,
    Player as PlayerModel,
    Group as GroupModel,
    Bracket as BracketModel
)
from app.services.tournament.tournament import Tournament as TournamentOrchestrator
from app.services.tournament.setupwizard import SetupWizard


class TournamentManagementService:

    def __init__(
            self,
            tournament_id: int,
            organizer_id: int | None,
        ) -> None:

        self.tournament_id = tournament_id
        self.organizer_id = organizer_id


    def can_manage(self) -> bool:
        if self.organizer_id is None:
            return False

        tournament = TournamentModel.query.get(self.tournament_id)

        if not tournament:
            return False

        return tournament.organizer_id == self.organizer_id


    def has_finished_match(self) -> bool:
        finished_match = MatchModel.query.filter_by(
            tournament_id=self.tournament_id,
            is_finished=True
        ).first()

        return finished_match is not None

    def can_reconfigure(self) -> bool:
        return self.can_manage() and not self.has_finished_match()

    def can_delete(self) -> bool:
        return self.can_reconfigure()

    def delete_tournament(self)-> bool:
        if not self.can_delete():
            return False

        tournament= TournamentModel.query.get(self.tournament_id)

        if not tournament:
            return False

        try:
            self._delete_tournament_structure(tournament)


            # 5. Samotný turnaj
            db.session.delete(tournament)
            db.session.commit()
            return True

        except Exception:
            db.session.rollback()
            raise

    def load_into_wizard(self) -> SetupWizard | None:
        if not self.can_reconfigure():
            return None

        tournament = TournamentModel.query.get(self.tournament_id)

        if not tournament:
            return None

        wizard = SetupWizard()

        wizard.name = tournament.name
        wizard.date = tournament.date.strftime("%Y-%m-%d")
        wizard.location = tournament.location or ""

        wizard.tournament_format = tournament.tournament_format
        wizard.include_in_global_stats = tournament.include_in_global_stats

        wizard.group_match_format = tournament.group_match_format
        wizard.group_elimination_action = tournament.group_elimination_action
        wizard.playoff_match_format = tournament.playoff_match_format
        wizard.playoff_elimination_action = tournament.playoff_elimination_action


        groups = (
            tournament.groups
            .filter_by(is_consolation=False)
            .all()
        )

        wizard.groups = {}

        for group in groups:
            letter = group.name.replace("Skupina ","").strip()

            wizard.groups[letter] = [
                player.name
                for player in group.players
            ]

        if wizard.is_single_group:
            wizard.single_group_playoff_count = (
                tournament.advance_per_group or 0
            )

        else:
            wizard.advance_per_group = tournament.advance_per_group

        return wizard

    def rebuild_tournamnet(self,wizard: SetupWizard) -> bool:
        if not self.can_reconfigure():
            return False

        tournament = TournamentModel.query.get(self.tournament_id)

        if not tournament:
            return False

        try:
            self._delete_tournament_structure(tournament)

            TournamentOrchestrator(
                setup=wizard,
                tournament_id=self.tournament_id
            )

            return True
        except Exception:
            db.session.rollback()
            raise




    def _delete_tournament_structure(self, tournament) -> None:
        # Tournament může ukazovat na vítěze, kterého budeme mazat
        tournament.winner_id = None
        db.session.flush()

        matches = MatchModel.query.filter_by(
            tournament_id=self.tournament_id
        ).all()

        for match in matches:
            db.session.delete(match)

        players = PlayerModel.query.filter_by(
            tournament_id=self.tournament_id
        ).all()

        for player in players:
            db.session.delete(player)

        groups = GroupModel.query.filter_by(
            tournament_id=self.tournament_id
        ).all()

        for group in groups:
            db.session.delete(group)

        brackets = BracketModel.query.filter_by(
            tournament_id=self.tournament_id
        )

        for bracket in brackets:
            db.session.delete(bracket)

        db.session.flush()