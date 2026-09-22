# app/services/player_stats.py
from datetime import datetime, timedelta
import sqlalchemy.orm
from sqlalchemy import or_, and_
from app.models.models import (
    db, Player as PlayerModel, GlobalPlayer as GlobalPlayerModel,
    Match as MatchModel, Tournament as TournamentModel,
    PlayoffStats as PlayoffStatsModel, ConsolationStats as ConsolationStatsModel
)
from app.services.stats.match_stats import MatchStatsService
import re


class PlayerStatsService:

    @staticmethod
    def get_player_profile_data(player_id, request_args):
        player = GlobalPlayerModel.query.get_or_404(player_id)
        local_player_ids = [p.id for p in PlayerModel.query.filter_by(global_player_id=player.id).all()]
        active_tab = request_args.get("tab", "overall")

        # Přednačtení dat přesunuto sem nahoru
        stats_map = PlayerStatsService._preload_player_stats()
        all_global_players = GlobalPlayerModel.query.all()

        # Nyní předáváme player_id a stats_map do metody
        tournaments_data = PlayerStatsService._get_tournaments_data(local_player_ids, player.id, stats_map)

        best_rank = None
        for t in tournaments_data:
            rank_str = str(t['rank'])
            match = re.search(r'\d+', rank_str)
            if match:
                r_val = int(match.group())
                if best_rank is None or r_val < best_rank:
                    best_rank = r_val

        context = {
            "player": player,
            "current_rank": PlayerStatsService._calculate_current_rank(player),
            "win_rate": PlayerStatsService._calculate_win_rate(player),
            "best_rank": best_rank,
            "tournaments_data": tournaments_data,
            **PlayerStatsService._get_rivalry_and_form(local_player_ids),
            **PlayerStatsService._get_chart_data(player, stats_map, all_global_players),
            "matches_data": PlayerStatsService._get_matches_data(local_player_ids),
            "h2h_data": PlayerStatsService._get_h2h_data(player, request_args, stats_map,
                                                         all_global_players),
            "active_tab": active_tab,
        }

        PlayerStatsService._apply_tab_filtering(context, request_args)

        return context

    @staticmethod
    def _preload_player_stats():
        """
        Přednačte body a umístění všech hráčů ze všech turnajů do slovníku.
        Struktura: {global_player_id: {tournament_id: {'date': date, 'points': int, 'rank': int, 'is_consolation': bool}}}
        """
        stats_map = {}

        query = db.session.query(
            PlayerModel.global_player_id,
            TournamentModel.id.label('tournament_id'),
            TournamentModel.date,
            PlayoffStatsModel.points_gained.label('playoff_points'),
            PlayoffStatsModel.final_rank.label('playoff_rank'),
            ConsolationStatsModel.final_rank.label('consolation_rank')
        ).join(TournamentModel, PlayerModel.tournament_id == TournamentModel.id) \
            .outerjoin(PlayoffStatsModel, PlayerModel.id == PlayoffStatsModel.player_id) \
            .outerjoin(ConsolationStatsModel, PlayerModel.id == ConsolationStatsModel.player_id) \
            .filter(TournamentModel.is_finished == True).all()

        for gp_id, t_id, t_date, p_pts, p_rank, c_rank in query:
            if not gp_id or not t_date:
                continue

            date_val = t_date.date() if hasattr(t_date, 'date') else t_date

            # Body má pouze playoff, útěcha dává 0 bodů
            pts = p_pts if p_pts is not None else 0

            # Určení finálního ranku a toho, zda pochází z útěchy
            final_rank = p_rank
            is_consolation = False

            if p_rank is None and c_rank is not None:
                final_rank = c_rank
                is_consolation = True

            if gp_id not in stats_map:
                stats_map[gp_id] = {}
            stats_map[gp_id][t_id] = {
                'date': date_val,
                'points': pts,
                'rank': final_rank,
                'is_consolation': is_consolation
            }

        return stats_map

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
        # Pridáme joinedload pro rychlejší přístup k datům protivníka bez N+1
        matches = MatchModel.query.options(
            sqlalchemy.orm.joinedload(MatchModel.player_a),
            sqlalchemy.orm.joinedload(MatchModel.player_b)
        ).filter(
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
            freq_id = max(opponents_stats,
                          key=lambda k: opponents_stats[k]["wins_against"] + opponents_stats[k]["losses_against"])
            if (opponents_stats[freq_id]["wins_against"] + opponents_stats[freq_id]["losses_against"]) > 0:
                most_frequent_opponent = opponents_stats[freq_id]

            fav_id = max(opponents_stats, key=lambda k: opponents_stats[k]["wins_against"])
            if opponents_stats[fav_id]["wins_against"] > 0:
                favorite_opponent = opponents_stats[fav_id]

            nem_id = max(opponents_stats, key=lambda k: opponents_stats[k]["losses_against"])
            if opponents_stats[nem_id]["losses_against"] > 0:
                nemesis = opponents_stats[nem_id]

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
    def _get_chart_data(player, stats_map, all_global_players):
        local_players_chronological = PlayerModel.query.filter_by(global_player_id=player.id) \
            .join(TournamentModel, PlayerModel.tournament_id == TournamentModel.id) \
            .filter(TournamentModel.is_finished == True) \
            .order_by(TournamentModel.date.asc(), TournamentModel.id.asc()) \
            .all()

        chart_labels = []
        chart_ranks = []
        chart_points = []
        chart_global_ranks = []

        player_stats = stats_map.get(player.id, {})

        for lp in local_players_chronological:
            t_id = lp.tournament.id
            chart_labels.append(lp.tournament.name)

            # Čtení přednačtených hodnot ze stats_map
            t_stats = player_stats.get(t_id, {})
            chart_ranks.append(t_stats.get('rank'))
            chart_points.append(t_stats.get('points', 0))

            t_date = lp.tournament.date
            if hasattr(t_date, 'date'):
                t_date = t_date.date()

            g_rank = PlayerStatsService._calculate_global_rank_at_date(player.id, t_date, all_global_players, stats_map)
            chart_global_ranks.append(g_rank)

        return {
            "chart_labels": chart_labels,
            "chart_ranks": chart_ranks,
            "chart_points": chart_points,
            "chart_global_ranks": chart_global_ranks
        }

    @staticmethod
    def _get_tournaments_data(local_player_ids, global_player_id, stats_map):
        player_tournaments = PlayerModel.query.filter(PlayerModel.id.in_(local_player_ids)) \
            .join(TournamentModel, PlayerModel.tournament_id == TournamentModel.id) \
            .order_by(TournamentModel.date.desc(), TournamentModel.id.desc()) \
            .all()

        player_stats = stats_map.get(global_player_id, {})

        tournaments_data = []
        for lp in player_tournaments:
            t_id = lp.tournament.id
            t_stats = player_stats.get(t_id, {})

            p_rank = t_stats.get('rank')
            points = t_stats.get('points', 0)
            is_consolation = t_stats.get('is_consolation', False)

            rank_str = "-"
            if p_rank is not None:
                if is_consolation:
                    rank_str = f"{p_rank}. místo (Útěcha)"
                else:
                    rank_str = f"{p_rank}. místo"

            tournaments_data.append({
                "tournament_name": lp.tournament.name,
                "tournament_date": lp.tournament.date,
                "tournament_id": t_id,
                "rank": rank_str,
                "points": points
            })
        return tournaments_data

    @staticmethod
    def _get_matches_data(local_player_ids):
        PlayerOpponent = sqlalchemy.orm.aliased(PlayerModel)

        # Omezíme načítaná data jen na to, co potřebujeme
        # a zajistíme joinedload na oponenta a turnaj, abychom zamezili N+1 při iteraci
        matches = MatchModel.query.options(
            sqlalchemy.orm.joinedload(MatchModel.tournament)
        ).join(
            PlayerOpponent,
            or_(
                and_(MatchModel.player_a_id == PlayerOpponent.id, MatchModel.player_a_id.notin_(local_player_ids)),
                and_(MatchModel.player_b_id == PlayerOpponent.id, MatchModel.player_b_id.notin_(local_player_ids))
            ),
            isouter=True  # Použijeme OUTER JOIN, protože protivník (např. BYE) nemusí existovat
        ).filter(
            or_(MatchModel.player_a_id.in_(local_player_ids), MatchModel.player_b_id.in_(local_player_ids)),
            MatchModel.is_finished == True
        ).all()

        matches_data = []
        for m in matches:
            is_player_a = m.player_a_id in local_player_ids
            our_local_id = m.player_a_id if is_player_a else m.player_b_id

            # Opponent byl načten přes JOIN, nezpůsobí další dotaz
            opponent_local = m.player_b if is_player_a else m.player_a

            result = 'R' if m.winner_id is None else ('V' if m.winner_id == our_local_id else 'P')

            # Většinou je turnaj rovnou na zápase, pokud jsi optimalizoval strukturu.
            # Jinak se pořád vyplatí používat .tournament z nadřazených objektů
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
    def _get_h2h_data(player, request_args, stats_map, all_global_players):
        selected_opponent_id = request_args.get("opponent_id", type=int)
        if not selected_opponent_id:
            return None

        selected_opponent = GlobalPlayerModel.query.get(selected_opponent_id)
        if not selected_opponent:
            return None

        base_h2h_stats = MatchStatsService.calculate_h2h_balance(player.id, selected_opponent_id)

        match_history = []
        for mh in base_h2h_stats["matches"]:
            match_history.append({
                "tournament_name": mh["tournament_name"],
                "tournament_id": mh["tournament_id"],
                "phase": mh["phase"],
                "score": mh["score"],
                "result": mh["result_for_a"]
            })

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

        player_stats = stats_map.get(player.id, {})
        opp_stats = stats_map.get(selected_opponent_id, {})

        for st in shared_tournaments:
            h2h_labels.append(st.name)
            t_date = st.date
            if hasattr(t_date, 'date'):
                t_date = t_date.date()

            # Ranky z přednačtených dat (žádné dotazy uvnitř cyklu)
            p_rank = player_stats.get(st.id, {}).get('rank')
            h2h_player_ranks.append(p_rank)

            opp_rank = opp_stats.get(st.id, {}).get('rank')
            h2h_opp_ranks.append(opp_rank)

            p_g_rank = PlayerStatsService._calculate_global_rank_at_date(player.id, t_date, all_global_players,
                                                                         stats_map)
            opp_g_rank = PlayerStatsService._calculate_global_rank_at_date(selected_opponent_id, t_date,
                                                                           all_global_players, stats_map)

            h2h_player_global_ranks.append(p_g_rank)
            h2h_opp_global_ranks.append(opp_g_rank)
        return {
            "opponent": selected_opponent,
            "wins": base_h2h_stats["wins_a"],
            "losses": base_h2h_stats["wins_b"],
            "draws": base_h2h_stats["draws"],
            "total": base_h2h_stats["total"],
            "win_rate": base_h2h_stats["win_rate_a"],
            "history": match_history,
            "chart_labels": h2h_labels,
            "player_ranks": h2h_player_ranks,
            "opp_ranks": h2h_opp_ranks,
            "player_global_ranks": h2h_player_global_ranks,
            "opp_global_ranks": h2h_opp_global_ranks
        }

    @staticmethod
    def _apply_tab_filtering(context, request_args):
        # Tato metoda zůstává beze změny, stará se jen o filtrování v paměti pro HTMX
        active_tab = context["active_tab"]

        tab_q = request_args.get("q", "").strip().lower()
        tab_sort_by = request_args.get("sort_by", "")
        tab_order = request_args.get("order", "desc")
        reverse_sort = (tab_order == "desc")

        context["tab_q"] = tab_q
        context["tab_sort_by"] = tab_sort_by
        context["tab_order"] = tab_order

        if active_tab == 'tournaments':
            if not tab_sort_by:
                tab_sort_by = "date"

            tournaments = context["tournaments_data"]
            if tab_q:
                filtered_tournaments = []
                for t in tournaments:
                    name = t['tournament_name'].lower()
                    rank = str(t['rank']).lower()

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

        elif active_tab == 'matches':
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
    def _calculate_global_rank_at_date(target_global_id, t_date, all_global_players, stats_map):
        if not t_date:
            return 1
        one_year_ago = t_date - timedelta(days=365)
        player_points_list = []

        for gp in all_global_players:
            gp_total = 0
            # player_tournaments je slovník {tournament_id: {...}}
            player_tournaments = stats_map.get(gp.id, {})

            for t_info in player_tournaments.values():
                p_date = t_info['date']
                pts = t_info['points']
                if one_year_ago <= p_date <= t_date:
                    gp_total += pts

            player_points_list.append((gp.id, gp_total))

        player_points_list.sort(key=lambda x: x[1], reverse=True)
        g_rank = 1
        for idx, (gp_id, pts) in enumerate(player_points_list):
            if gp_id == target_global_id:
                g_rank = idx + 1
                break
        return g_rank