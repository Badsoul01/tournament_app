import sqlalchemy
from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload
from app.models.models import Match as MatchModel, Player as PlayerModel, MatchResults as MatchResultsModel

class MatchStatsService:

    @staticmethod
    def get_match_detail_context(match_id: int) -> dict:
        match = MatchModel.query.get_or_404(match_id)
        sets = match.sets.order_by(MatchResultsModel.set_number).all() if hasattr(match, 'sets') else []

        stats_a = MatchStatsService._get_player_stats(match.player_a)
        stats_b = MatchStatsService._get_player_stats(match.player_b)

        if match.player_a and match.player_b and match.player_a.global_player_id and match.player_b.global_player_id:
            h2h_data = MatchStatsService.calculate_h2h_balance(
                match.player_a.global_player_id,
                match.player_b.global_player_id,
                up_to_match_id=match.id
            )
        else:
            h2h_data = {"wins_a": 0, "wins_b": 0, "draws": 0, "total": 0}

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
    def calculate_h2h_balance(global_id_a: int, global_id_b: int, up_to_match_id: int = None):
        """Univerzální metoda pro výpočet bilance mezi dvěma hráči."""
        if not global_id_a or not global_id_b:
            return {"wins_a": 0, "wins_b": 0, "draws": 0, "total": 0, "win_rate_a": 0, "matches": []}

        past_matches = MatchStatsService.get_h2h_matches(
            global_id_a, global_id_b, up_to_match_id=up_to_match_id
        )

        wins_a, wins_b, draws = 0, 0, 0
        match_history = []

        for hm in past_matches:
            # Díky joinedload v get_h2h_matches už nepotřebujeme stahovat loc_ids_a
            # Zjistíme naší pozici rovnou z připojeného modelu
            is_a_in_a = hm.player_a and hm.player_a.global_player_id == global_id_a
            our_local_id = hm.player_a_id if is_a_in_a else hm.player_b_id

            if hm.winner_id is None:
                draws += 1
                res_for_a = 'R'
            elif hm.winner_id == our_local_id:
                wins_a += 1
                res_for_a = 'V'
            else:
                wins_b += 1
                res_for_a = 'P'

            t_id, t_name = None, "-"
            if hasattr(hm, 'tournament') and hm.tournament:
                t_name = hm.tournament.name
                t_id = hm.tournament.id

            match_history.append({
                "tournament_name": t_name,
                "tournament_id": t_id,
                "phase": hm.phase_display_name if hasattr(hm, 'phase_display_name') else "-",
                "score": hm.formatted_score if hasattr(hm, 'formatted_score') else "-",
                "result_for_a": res_for_a,
                "raw_match": hm
            })

        total = wins_a + wins_b + draws
        win_rate_a = round((wins_a / total) * 100, 1) if total > 0 else 0

        return {
            "wins_a": wins_a,
            "wins_b": wins_b,
            "draws": draws,
            "total": total,
            "win_rate_a": win_rate_a,
            "matches": match_history
        }

    @staticmethod
    def get_h2h_matches(global_id_a: int, global_id_b: int, up_to_match_id: int = None):
        """Vrátí všechny vzájemné dokončené zápasy (plně optimalizováno proti N+1)."""
        PlayerA = sqlalchemy.orm.aliased(PlayerModel)
        PlayerB = sqlalchemy.orm.aliased(PlayerModel)

        # joinedload nám stáhne hráče a turnaj v tom samém dotazu,
        # takže cyklus v calculate_h2h_balance nevytváří zpoždění
        query = MatchModel.query.options(
            joinedload(MatchModel.player_a),
            joinedload(MatchModel.player_b),
            joinedload(MatchModel.tournament)
        ).join(PlayerA, MatchModel.player_a_id == PlayerA.id) \
         .join(PlayerB, MatchModel.player_b_id == PlayerB.id) \
         .filter(
            or_(
                and_(PlayerA.global_player_id == global_id_a, PlayerB.global_player_id == global_id_b),
                and_(PlayerA.global_player_id == global_id_b, PlayerB.global_player_id == global_id_a)
            ),
            MatchModel.is_finished == True
        )

        if up_to_match_id:
            query = query.filter(MatchModel.id <= up_to_match_id)

        return query.all()