# app/services/stats_player_detail.py
from datetime import datetime, timedelta
from sqlalchemy import or_
from app.models.models import (
    db, Player as PlayerModel, GlobalPlayer as GlobalPlayerModel,
    Match as MatchModel, Tournament as TournamentModel,
    PlayoffStats as PlayoffStatsModel, ConsolationStats as ConsolationStatsModel
)
from app.services.stats.match_stats import MatchStatsService


class PlayerStatsService:

    @staticmethod
    def get_player_profile_data(player_id, request_args):
        # 1. Základní entity
        player = GlobalPlayerModel.query.get_or_404(player_id)
        local_player_ids = [p.id for p in PlayerModel.query.filter_by(global_player_id=player.id).all()]
        active_tab = request_args.get("tab", "obecne")

        tournaments_data = PlayerStatsService._get_tournaments_data(local_player_ids)

        # Výpočet nejlepšího umístění (nejnižší číslo ranku, např. 1. místo)
        best_rank = None
        for t in tournaments_data:
            rank_str = str(t['rank'])
            # Extrahujeme číslo z řetězce typu "1. místo" nebo "2. místo (Útěcha)"
            import re
            match = re.search(r'\d+', rank_str)
            if match:
                r_val = int(match.group())
                if best_rank is None or r_val < best_rank:
                    best_rank = r_val

        # 2. Skládání kontextu přes specializované metody
        context = {
            "player": player,
            "current_rank": PlayerStatsService._calculate_current_rank(player),
            "win_rate": PlayerStatsService._calculate_win_rate(player),
            "best_rank": best_rank,
            "tournaments_data": tournaments_data,
            **PlayerStatsService._get_rivalry_and_form(local_player_ids),
            **PlayerStatsService._get_chart_data(player),
            "matches_data": PlayerStatsService._get_matches_data(local_player_ids),
            "h2h_data": PlayerStatsService._get_h2h_data(player, local_player_ids, request_args),
            "active_tab": active_tab,
        }

        # 3. Filtrování a řazení pro aktivní tabulku
        PlayerStatsService._apply_tab_filtering(context, request_args)

        return context

    @staticmethod
    def _calculate_current_rank(player):
        all_players = GlobalPlayerModel.query.all()
        all_players.sort(key=lambda p: p.total_points, reverse=True)
        for idx, p in enumerate(all_players):
            if p.id == player.id:
                return idx + 1
        return 1

    @staticmethod
    def _calculate_win_rate(player):
        if player.matches_played > 0:
            return round((player.matches_won / player.matches_played) * 100, 1)
        return 0

    @staticmethod
    def _get_rivalry_and_form(local_player_ids):
        matches = MatchModel.query.filter(
            or_(MatchModel.player_a_id.in_(local_player_ids), MatchModel.player_b_id.in_(local_player_ids)),
            MatchModel.is_finished == True,
            MatchModel.winner_id.isnot(None)
        ).all()

        opponents_stats = {}
        for m in matches:
            is_player_a = m.player_a_id in local_player_ids
            our_local_id = m.player_a_id if is_player_a else m.player_b_id
            opponent_local = m.player_b if is_player_a else m.player_a

            if not opponent_local or not opponent_local.global_player_id:
                continue

            opp_global_id = opponent_local.global_player_id
            if opp_global_id not in opponents_stats:
                opponents_stats[opp_global_id] = {
                    "id": opp_global_id,
                    "name": opponent_local.name,
                    "wins_against": 0,
                    "losses_against": 0
                }

            if m.winner_id == our_local_id:
                opponents_stats[opp_global_id]["wins_against"] += 1
            else:
                opponents_stats[opp_global_id]["losses_against"] += 1

        most_frequent_opponent, favorite_opponent, nemesis = None, None, None
        if opponents_stats:
            # Nejčastější soupeř (součet výher a proher)
            freq_id = max(opponents_stats,
                          key=lambda k: opponents_stats[k]["wins_against"] + opponents_stats[k]["losses_against"])
            if (opponents_stats[freq_id]["wins_against"] + opponents_stats[freq_id]["losses_against"]) > 0:
                most_frequent_opponent = opponents_stats[freq_id]

            # Nejvíce výher proti
            fav_id = max(opponents_stats, key=lambda k: opponents_stats[k]["wins_against"])
            if opponents_stats[fav_id]["wins_against"] > 0:
                favorite_opponent = opponents_stats[fav_id]

            # Nejvíce proher proti (Nemesis)
            nem_id = max(opponents_stats, key=lambda k: opponents_stats[k]["losses_against"])
            if opponents_stats[nem_id]["losses_against"] > 0:
                nemesis = opponents_stats[nem_id]

        # Posledních 5 zápasů (forma)
        recent_matches = MatchModel.query.join(TournamentModel).filter(
            or_(MatchModel.player_a_id.in_(local_player_ids), MatchModel.player_b_id.in_(local_player_ids)),
            MatchModel.is_finished == True
        ).order_by(TournamentModel.date.desc(), MatchModel.id.desc()).limit(5).all()

        recent_form = []
        for rm in recent_matches:
            our_local_id = rm.player_a_id if rm.player_a_id in local_player_ids else rm.player_b_id
            if rm.winner_id == our_local_id:
                recent_form.append('V')
            elif rm.winner_id is None:
                recent_form.append('R')
            else:
                recent_form.append('P')
        recent_form.reverse()

        return {
            "most_frequent_opponent": most_frequent_opponent,
            "favorite_opponent": favorite_opponent,
            "nemesis": nemesis,
            "recent_form": recent_form,
            "opponents_list": sorted(opponents_stats.values(), key=lambda x: x['name'])
        }

    @staticmethod
    def _get_chart_data(player):
        local_players_chronological = PlayerModel.query.filter_by(global_player_id=player.id) \
            .join(TournamentModel, PlayerModel.tournament_id == TournamentModel.id) \
            .filter(TournamentModel.is_finished == True) \
            .order_by(TournamentModel.date.asc(), TournamentModel.id.asc()) \
            .all()

        chart_labels = []
        chart_ranks = []
        chart_points = []
        chart_global_ranks = []

        all_global_players = GlobalPlayerModel.query.all()

        for lp in local_players_chronological:
            chart_labels.append(lp.tournament.name)

            p_stats = PlayoffStatsModel.query.filter_by(player_id=lp.id).first()
            c_stats = ConsolationStatsModel.query.filter_by(player_id=lp.id).first()

            rank = None
            points = 0

            if p_stats and p_stats.final_rank is not None:
                rank = p_stats.final_rank
                points = p_stats.points_gained or 0
            elif c_stats and c_stats.final_rank is not None:
                rank = c_stats.final_rank

            chart_ranks.append(rank)
            chart_points.append(points)

            # --- VÝPOČET CELKOVÉHO RANKU K DATU TOHOTO TURNAJE ---
            t_date = lp.tournament.date
            if hasattr(t_date, 'date'):
                t_date = t_date.date()

            one_year_ago = t_date - timedelta(days=365) if t_date else None
            player_points_list = []

            for gp in all_global_players:
                gp_total = 0
                for entry in gp.tournament_entries:
                    if entry.tournament and entry.tournament.is_finished:
                        e_date = entry.tournament.date
                        if hasattr(e_date, 'date'):
                            e_date = e_date.date()
                        if e_date and t_date and one_year_ago and one_year_ago <= e_date <= t_date:
                            ps = PlayoffStatsModel.query.filter_by(player_id=entry.id).first()
                            cs = ConsolationStatsModel.query.filter_by(player_id=entry.id).first()
                            if ps and ps.points_gained:
                                gp_total += ps.points_gained
                            elif cs and hasattr(cs, 'points_gained') and cs.points_gained:
                                gp_total += cs.points_gained
                player_points_list.append((gp.id, gp_total))

            player_points_list.sort(key=lambda x: x[1], reverse=True)
            g_rank = 1
            for idx, (gp_id, pts) in enumerate(player_points_list):
                if gp_id == player.id:
                    g_rank = idx + 1
                    break
            chart_global_ranks.append(g_rank)

        return {
            "chart_labels": chart_labels,
            "chart_ranks": chart_ranks,
            "chart_points": chart_points,
            "chart_global_ranks": chart_global_ranks
        }

    @staticmethod
    def _get_tournaments_data(local_player_ids):
        player_tournaments = PlayerModel.query.filter(PlayerModel.id.in_(local_player_ids)) \
            .join(TournamentModel, PlayerModel.tournament_id == TournamentModel.id) \
            .order_by(TournamentModel.date.desc(), TournamentModel.id.desc()) \
            .all()

        tournaments_data = []
        for lp in player_tournaments:
            p_stats = PlayoffStatsModel.query.filter_by(player_id=lp.id).first()
            c_stats = ConsolationStatsModel.query.filter_by(player_id=lp.id).first()

            rank, points = "-", 0
            if p_stats and p_stats.final_rank is not None:
                rank, points = f"{p_stats.final_rank}. místo", (p_stats.points_gained or 0)
            elif c_stats and c_stats.final_rank is not None:
                rank = f"{c_stats.final_rank}. místo (Útěcha)"

            tournaments_data.append({
                "tournament_name": lp.tournament.name,
                "tournament_date": lp.tournament.date,
                "tournament_id": lp.tournament.id,
                "rank": rank,
                "points": points
            })
        return tournaments_data

    @staticmethod
    def _get_matches_data(local_player_ids):
        all_player_matches = MatchModel.query.filter(
            or_(MatchModel.player_a_id.in_(local_player_ids), MatchModel.player_b_id.in_(local_player_ids)),
            MatchModel.is_finished == True
        ).all()

        matches_data = []
        for m in all_player_matches:
            is_player_a = m.player_a_id in local_player_ids
            our_local_id = m.player_a_id if is_player_a else m.player_b_id
            opponent_local = m.player_b if is_player_a else m.player_a

            result = 'R' if m.winner_id is None else ('V' if m.winner_id == our_local_id else 'P')

            t_name, t_id = "-", None
            if hasattr(m, 'tournament') and m.tournament:
                t_name, t_id = m.tournament.name, m.tournament.id
            elif hasattr(m, 'group') and m.group and m.group.tournament:
                t_name, t_id = m.group.tournament.name, m.group.tournament.id
            elif hasattr(m, 'bracket') and m.bracket and m.bracket.tournament:
                t_name, t_id = m.bracket.tournament.name, m.bracket.tournament.id

            matches_data.append({
                "tournament_name": t_name, "tournament_id": t_id,
                "phase": m.phase_display_name,
                "opponent_name": opponent_local.name if opponent_local else "BYE",
                "opponent_id": opponent_local.global_player_id if opponent_local else None,
                "score": m.formatted_score, "result": result
            })
        return matches_data

    @staticmethod
    def _get_h2h_data(player, local_player_ids, request_args):
        selected_opponent_id = request_args.get("opponent_id", type=int)
        if not selected_opponent_id:
            return None

        selected_opponent = GlobalPlayerModel.query.get(selected_opponent_id)
        if not selected_opponent:
            return None

        h2h_matches = MatchStatsService.get_h2h_matches(player.id, selected_opponent_id)

        wins, losses, draws = 0, 0, 0
        match_history = []
        for hm in h2h_matches:
            is_player_a = hm.player_a_id in local_player_ids
            our_local_id = hm.player_a_id if is_player_a else hm.player_b_id

            if hm.winner_id is None:
                draws, res = draws + 1, 'R'
            elif hm.winner_id == our_local_id:
                wins, res = wins + 1, 'V'
            else:
                losses, res = losses + 1, 'P'

            # Zjištění ID turnaje pro bezpečné řazení
            t_id = None
            t_name = "-"
            if hasattr(hm, 'tournament') and hm.tournament:
                t_name = hm.tournament.name
                t_id = hm.tournament.id

            match_history.append({
                "tournament_name": t_name,
                "tournament_id": t_id,
                "phase": hm.phase_display_name,
                "score": hm.formatted_score,
                "result": res
            })

        total = wins + losses + draws
        win_rate_h2h = round((wins / total) * 100, 1) if total > 0 else 0

        # --- SDÍLENÉ TURNAJE PRO H2H GRAFY ---
        shared_tournaments = TournamentModel.query \
            .join(PlayerModel, TournamentModel.id == PlayerModel.tournament_id) \
            .filter(TournamentModel.is_finished == True) \
            .filter(or_(PlayerModel.global_player_id == player.id,
                        PlayerModel.global_player_id == selected_opponent_id)) \
            .group_by(TournamentModel.id) \
            .having(db.func.count(db.func.distinct(PlayerModel.global_player_id)) == 2) \
            .order_by(TournamentModel.date.asc(), TournamentModel.id.asc()) \
            .all()

        h2h_labels = []
        h2h_player_ranks = []
        h2h_opp_ranks = []
        h2h_player_global_ranks = []
        h2h_opp_global_ranks = []

        all_global_players = GlobalPlayerModel.query.all()

        for st in shared_tournaments:
            h2h_labels.append(st.name)
            t_date = st.date
            if hasattr(t_date, 'date'):
                t_date = t_date.date()

            # Rank hlavního hráče v turnaji
            p_entry = PlayerModel.query.filter_by(tournament_id=st.id, global_player_id=player.id).first()
            p_rank = None
            if p_entry:
                ps = PlayoffStatsModel.query.filter_by(player_id=p_entry.id).first()
                cs = ConsolationStatsModel.query.filter_by(player_id=p_entry.id).first()
                if ps and ps.final_rank is not None:
                    p_rank = ps.final_rank
                elif cs and cs.final_rank is not None:
                    p_rank = cs.final_rank
            h2h_player_ranks.append(p_rank)

            # Rank soupeře v turnaji
            opp_entry = PlayerModel.query.filter_by(tournament_id=st.id, global_player_id=selected_opponent_id).first()
            opp_rank = None
            if opp_entry:
                ops = PlayoffStatsModel.query.filter_by(player_id=opp_entry.id).first()
                ocs = ConsolationStatsModel.query.filter_by(player_id=opp_entry.id).first()
                if ops and ops.final_rank is not None:
                    opp_rank = ops.final_rank
                elif ocs and ocs.final_rank is not None:
                    opp_rank = ocs.final_rank
            h2h_opp_ranks.append(opp_rank)

            # Globální ranky k datu turnaje
            p_g_rank = PlayerStatsService._calculate_global_rank_at_date(player.id, t_date, all_global_players)
            opp_g_rank = PlayerStatsService._calculate_global_rank_at_date(selected_opponent_id, t_date,
                                                                           all_global_players)
            h2h_player_global_ranks.append(p_g_rank)
            h2h_opp_global_ranks.append(opp_g_rank)

        return {
            "opponent": selected_opponent,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "total": total,
            "win_rate": win_rate_h2h,
            "history": match_history,
            "chart_labels": h2h_labels,
            "player_ranks": h2h_player_ranks,
            "opp_ranks": h2h_opp_ranks,
            "player_global_ranks": h2h_player_global_ranks,
            "opp_global_ranks": h2h_opp_global_ranks
        }

    @staticmethod
    def _apply_tab_filtering(context, request_args):
        active_tab = context["active_tab"]

        tab_q = request_args.get("q", "").strip().lower()
        tab_sort_by = request_args.get("sort_by", "")
        tab_order = request_args.get("order", "desc")
        reverse_sort = (tab_order == "desc")

        context["tab_q"] = tab_q
        context["tab_sort_by"] = tab_sort_by
        context["tab_order"] = tab_order

        if active_tab == 'turnaje':
            if not tab_sort_by:
                tab_sort_by = "date"

            tournaments = context["tournaments_data"]
            if tab_q:
                filtered_tournaments = []
                for t in tournaments:
                    name = t['tournament_name'].lower()
                    rank = str(t['rank']).lower()

                    # Převedeme datum na řetězce pro možnost vyhledávání (např. "15.06.2026" nebo "2026")
                    date_str = ""
                    if t['tournament_date']:
                        if hasattr(t['tournament_date'], 'strftime'):
                            d_dot = t['tournament_date'].strftime('%d.%m.%Y').lower()
                            d_iso = t['tournament_date'].strftime('%Y-%m-%d').lower()
                            date_str = f"{d_dot} {d_iso}"
                        else:
                            date_str = str(t['tournament_date']).lower()

                    if tab_q in name or tab_q in rank or tab_q in date_str:
                        filtered_tournaments.append(t)
                tournaments = filtered_tournaments

            if tab_sort_by == "name":
                tournaments.sort(key=lambda x: x['tournament_name'], reverse=reverse_sort)
            elif tab_sort_by == "rank":
                tournaments.sort(key=lambda x: int(str(x['rank']).split('.')[0]) if str(x['rank']).split('.')[
                    0].isdigit() else 999, reverse=reverse_sort)
            elif tab_sort_by == "points":
                tournaments.sort(key=lambda x: x['points'], reverse=reverse_sort)
            else:
                tournaments.sort(key=lambda x: x['tournament_date'] or datetime.min.date(), reverse=reverse_sort)

            context["tournaments_data"] = tournaments

        elif active_tab == 'zapasy':
            if not tab_sort_by:
                tab_sort_by = "tournament"

            matches = context["matches_data"]
            if tab_q:
                matches = [m for m in matches if
                           tab_q in m['tournament_name'].lower() or tab_q in m['phase'].lower() or tab_q in m[
                               'opponent_name'].lower()]

            if tab_sort_by == "phase":
                matches.sort(key=lambda x: x['phase'], reverse=reverse_sort)
            elif tab_sort_by == "opponent":
                matches.sort(key=lambda x: x['opponent_name'], reverse=reverse_sort)
            elif tab_sort_by == "score":
                matches.sort(key=lambda x: x['score'], reverse=reverse_sort)
            elif tab_sort_by == "result":
                matches.sort(key=lambda x: x['result'], reverse=reverse_sort)
            else:
                matches.sort(key=lambda x: x['tournament_id'] or 0, reverse=reverse_sort)

            context["matches_data"] = matches

        elif active_tab == 'h2h' and context["h2h_data"]:
            if not tab_sort_by:
                tab_sort_by = "tournament"

            h2h = context["h2h_data"]
            history = h2h['history']

            if tab_q:
                history = [hm for hm in history if
                           tab_q in hm['tournament_name'].lower() or tab_q in hm['phase'].lower()]

            if tab_sort_by == "phase":
                history.sort(key=lambda x: x['phase'], reverse=reverse_sort)
            elif tab_sort_by == "score":
                history.sort(key=lambda x: x['score'], reverse=reverse_sort)
            elif tab_sort_by == "result":
                history.sort(key=lambda x: x['result'], reverse=reverse_sort)
            else:
                history.sort(key=lambda x: x['tournament_id'] or 0, reverse=reverse_sort)

            h2h['history'] = history

    @staticmethod
    def _calculate_global_rank_at_date(target_global_id, t_date, all_global_players):
        """Pomocná metoda pro výpočet globálního ranku hráče k danému datu."""
        if not t_date:
            return 1
        one_year_ago = t_date - timedelta(days=365)
        player_points_list = []

        for gp in all_global_players:
            gp_total = 0
            for entry in gp.tournament_entries:
                if entry.tournament and entry.tournament.is_finished:
                    e_date = entry.tournament.date
                    if hasattr(e_date, 'date'):
                        e_date = e_date.date()
                    if e_date and one_year_ago <= e_date <= t_date:
                        ps = PlayoffStatsModel.query.filter_by(player_id=entry.id).first()
                        cs = ConsolationStatsModel.query.filter_by(player_id=entry.id).first()
                        if ps and ps.points_gained:
                            gp_total += ps.points_gained
                        elif cs and hasattr(cs, 'points_gained') and cs.points_gained:
                            gp_total += cs.points_gained
            player_points_list.append((gp.id, gp_total))

        player_points_list.sort(key=lambda x: x[1], reverse=True)
        g_rank = 1
        for idx, (gp_id, pts) in enumerate(player_points_list):
            if gp_id == target_global_id:
                g_rank = idx + 1
                break
        return g_rank