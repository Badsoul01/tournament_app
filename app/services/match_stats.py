from app.models.models import Match as MatchModel, Player as PlayerModel, MatchResults as MatchResultsModel
from sqlalchemy import or_, and_

class MatchStatsService:

    @staticmethod
    def get_match_detail_context(match_id: int) -> dict:
        """Připraví kompletní kontext pro detail zápasu včetně setů, win-rate a H2H bilance."""
        match = MatchModel.query.get_or_404(match_id)
        sets = match.sets.order_by(MatchResultsModel.set_number).all() if hasattr(match, 'sets') else []

        stats_a = MatchStatsService._get_player_stats(match.player_a)
        stats_b = MatchStatsService._get_player_stats(match.player_b)
        h2h_data = MatchStatsService._calculate_h2h(match)

        return {
            "match": match,
            "sets": sets,
            "stats_a": stats_a,
            "stats_b": stats_b,
            "h2h_data": h2h_data
        }

    @staticmethod
    def _get_player_stats(player):
        if not player or not player.global_profile:
            return {"wins": 0, "losses": 0, "win_rate": 0}
        gp = player.global_profile
        played = gp.matches_played or 0
        won = gp.matches_won or 0
        rate = round((won / played) * 100, 1) if played > 0 else 0
        return {"wins": won, "losses": gp.matches_lost or 0, "win_rate": rate}

    @staticmethod
    def _calculate_h2h(match):
        h2h_wins_a, h2h_wins_b, h2h_draws = 0, 0, 0

        if match.player_a and match.player_b and match.player_a.global_player_id and match.player_b.global_player_id:
            past_matches = MatchStatsService.get_h2h_matches(
                match.player_a.global_player_id,
                match.player_b.global_player_id,
                up_to_match_id=match.id
            )

            loc_ids_a = [p.id for p in
                         PlayerModel.query.filter_by(global_player_id=match.player_a.global_player_id).all()]

            for pm in past_matches:
                is_a_in_a = pm.player_a_id in loc_ids_a
                our_id = pm.player_a_id if is_a_in_a else pm.player_b_id

                if pm.winner_id is None:
                    h2h_draws += 1
                elif pm.winner_id == our_id:
                    h2h_wins_a += 1
                else:
                    h2h_wins_b += 1

        return {
            "wins_a": h2h_wins_a,
            "wins_b": h2h_wins_b,
            "draws": h2h_draws,
            "total": h2h_wins_a + h2h_wins_b + h2h_draws
        }

    @staticmethod
    def get_h2h_matches(global_id_a: int, global_id_b: int, up_to_match_id: int = None):
        """Vrátí všechny vzájemné dokončené zápasy mezi dvěma globálními hráči."""
        loc_ids_a = [p.id for p in PlayerModel.query.filter_by(global_player_id=global_id_a).all()]
        loc_ids_b = [p.id for p in PlayerModel.query.filter_by(global_player_id=global_id_b).all()]

        if not loc_ids_a or not loc_ids_b:
            return []

        query = MatchModel.query.filter(
            or_(
                and_(MatchModel.player_a_id.in_(loc_ids_a), MatchModel.player_b_id.in_(loc_ids_b)),
                and_(MatchModel.player_a_id.in_(loc_ids_b), MatchModel.player_b_id.in_(loc_ids_a))
            ),
            MatchModel.is_finished == True
        )

        if up_to_match_id:
            query = query.filter(MatchModel.id <= up_to_match_id)

        return query.all()