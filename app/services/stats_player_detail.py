from datetime import datetime, timedelta
from sqlalchemy import or_, and_
from flask import request
from app.models.models import db,Player as PlayerModel, GlobalPlayer as GlobalPlayerModel, \
 Match as MatchModel, Tournament as TournamentModel, PlayoffStats as PlayoffStatsModel, ConsolationStats as ConsolationStatsModel

class PlayerStatsService:
    @staticmethod
    def get_player_profile_data(player_id,request_args):
        # 1. Načtení globálního hráče
        player = GlobalPlayerModel.query.get_or_404(player_id)

        # 2. Výpočet aktuálního ranku (upraveno pro dynamickou property total_points)
        all_players = GlobalPlayerModel.query.all()
        all_players.sort(key=lambda p: p.total_points, reverse=True)

        current_rank = 1
        for idx, p in enumerate(all_players):
            if p.id == player.id:
                current_rank = idx + 1
                break

        # 3. Výpočet Win Rate
        win_rate = 0
        if player.matches_played > 0:
            win_rate = round((player.matches_won / player.matches_played) * 100, 1)

        # 4. Získání všech "lokálních" ID tohoto hráče
        local_player_ids = [p.id for p in PlayerModel.query.filter_by(global_player_id=player.id).all()]

        # 5. Analýza soupeřů (Rivalita)
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
            opp_name = opponent_local.name

            if opp_global_id not in opponents_stats:
                # Ukládáme i ID pro budoucí odkaz v HTML
                opponents_stats[opp_global_id] = {"id": opp_global_id, "name": opp_name, "wins_against": 0,
                                                  "losses_against": 0}

            if m.winner_id == our_local_id:
                opponents_stats[opp_global_id]["wins_against"] += 1
            else:
                opponents_stats[opp_global_id]["losses_against"] += 1

        favorite_opponent = None
        nemesis = None

        if opponents_stats:
            fav_id = max(opponents_stats, key=lambda k: opponents_stats[k]["wins_against"])
            if opponents_stats[fav_id]["wins_against"] > 0:
                favorite_opponent = opponents_stats[fav_id]

            nem_id = max(opponents_stats, key=lambda k: opponents_stats[k]["losses_against"])
            if opponents_stats[nem_id]["losses_against"] > 0:
                nemesis = opponents_stats[nem_id]

        # 6. Aktuální forma (posledních 5 zápasů)
        recent_matches = MatchModel.query.join(TournamentModel).filter(
            or_(MatchModel.player_a_id.in_(local_player_ids), MatchModel.player_b_id.in_(local_player_ids)),
            MatchModel.is_finished == True
        ).order_by(TournamentModel.date.desc(), MatchModel.id.desc()).limit(5).all()

        recent_form = []
        for rm in recent_matches:
            is_player_a = rm.player_a_id in local_player_ids
            our_local_id = rm.player_a_id if is_player_a else rm.player_b_id

            if rm.winner_id == our_local_id:
                recent_form.append('V')  # Výhra
            elif rm.winner_id is None:
                recent_form.append('R')  # Remíza
            else:
                recent_form.append('P')  # Prohra

        # Otočíme pole, aby nejnovější zápas byl vpravo
        recent_form.reverse()

        # Vytvoření seřazeného seznamu soupeřů pro H2H dropdown
        opponents_list = sorted(opponents_stats.values(), key=lambda x: x['name'])

        # 7. Příprava dat pro grafy
        # Načteme všechny účasti hráče v dokončených turnajích, chronologicky od nejstaršího
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

            # Získáme rank a body (upřednostníme hlavní playoff před útěchou)
            if p_stats and p_stats.final_rank is not None:
                rank = p_stats.final_rank
                points = p_stats.points_gained or 0
            elif c_stats and c_stats.final_rank is not None:
                rank = c_stats.final_rank

            chart_ranks.append(rank)
            chart_points.append(points)

            # --- VÝPOČET CELKOVÉHO RANKU K DATU TÉTOHO TURNAJE ---
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

        # 8. Příprava dat pro záložku Turnaje
        player_tournaments = PlayerModel.query.filter_by(global_player_id=player.id) \
            .join(TournamentModel, PlayerModel.tournament_id == TournamentModel.id) \
            .order_by(TournamentModel.date.desc(), TournamentModel.id.desc()) \
            .all()

        tournaments_data = []
        for lp in player_tournaments:
            p_stats = PlayoffStatsModel.query.filter_by(player_id=lp.id).first()
            c_stats = ConsolationStatsModel.query.filter_by(player_id=lp.id).first()

            rank = "-"
            points = 0

            if p_stats and p_stats.final_rank is not None:
                rank = f"{p_stats.final_rank}. místo"
                points = p_stats.points_gained or 0
            elif c_stats and c_stats.final_rank is not None:
                rank = f"{c_stats.final_rank}. místo (Útěcha)"

            tournaments_data.append({
                "tournament_name": lp.tournament.name,
                "tournament_date": lp.tournament.date,
                "tournament_id": lp.tournament.id,
                "rank": rank,
                "points": points
            })

        # 9. Příprava dat pro záložku Zápasy
        all_player_matches = MatchModel.query.filter(
            or_(MatchModel.player_a_id.in_(local_player_ids), MatchModel.player_b_id.in_(local_player_ids)),
            MatchModel.is_finished == True
        ).all()

        matches_data = []
        for m in all_player_matches:
            is_player_a = m.player_a_id in local_player_ids

            our_local_id = m.player_a_id if is_player_a else m.player_b_id
            opponent_local = m.player_b if is_player_a else m.player_a

            opp_name = opponent_local.name if opponent_local else "BYE"
            opp_global_id = opponent_local.global_player_id if opponent_local else None

            # Určení výsledku pro našeho hráče
            if m.winner_id is None:
                result = 'R'
            elif m.winner_id == our_local_id:
                result = 'V'
            else:
                result = 'P'

            # Zjištění názvu turnaje přes bezpečné vazby
            tournament_name = "-"
            tournament_id = None
            if hasattr(m, 'tournament') and m.tournament:
                tournament_name = m.tournament.name
                tournament_id = m.tournament.id
            elif hasattr(m, 'group') and m.group and m.group.tournament:
                tournament_name = m.group.tournament.name
                tournament_id = m.group.tournament.id
            elif hasattr(m, 'bracket') and m.bracket and m.bracket.tournament:
                tournament_name = m.bracket.tournament.name
                tournament_id = m.bracket.tournament.id

            matches_data.append({
                "tournament_name": tournament_name,
                "tournament_id": tournament_id,
                "phase": m.phase_display_name,
                "opponent_name": opp_name,
                "opponent_id": opp_global_id,
                "score": m.formatted_score,
                "result": result
            })

        # 10. Příprava dat pro záložku Head-to-Head (H2H)
        selected_opponent_id = request.args.get("opponent_id", type=int)
        h2h_data = None

        if selected_opponent_id:
            selected_opponent = GlobalPlayerModel.query.get(selected_opponent_id)
            if selected_opponent:
                opp_local_ids = [p.id for p in
                                 PlayerModel.query.filter_by(global_player_id=selected_opponent_id).all()]

                h2h_matches = MatchModel.query.filter(
                    or_(
                        and_(MatchModel.player_a_id.in_(local_player_ids),
                             MatchModel.player_b_id.in_(opp_local_ids)),
                        and_(MatchModel.player_a_id.in_(opp_local_ids),
                             MatchModel.player_b_id.in_(local_player_ids))
                    ),
                    MatchModel.is_finished == True
                ).all()

                wins = 0
                losses = 0
                draws = 0
                match_history = []

                for hm in h2h_matches:
                    is_player_a = hm.player_a_id in local_player_ids
                    our_local_id = hm.player_a_id if is_player_a else hm.player_b_id

                    if hm.winner_id is None:
                        draws += 1
                        res = 'R'
                    elif hm.winner_id == our_local_id:
                        wins += 1
                        res = 'V'
                    else:
                        losses += 1
                        res = 'P'

                    tournament_name = "-"
                    tournament_id = None
                    if hasattr(hm, 'tournament') and hm.tournament:
                        tournament_name = hm.tournament.name
                        tournament_id = hm.tournament.id
                    elif hasattr(hm, 'group') and hm.group and hm.group.tournament:
                        tournament_name = hm.group.tournament.name
                        tournament_id = hm.group.tournament.id
                    elif hasattr(hm, 'bracket') and hm.bracket and hm.bracket.tournament:
                        tournament_name = hm.bracket.tournament.name
                        tournament_id = hm.bracket.tournament.id

                    match_history.append({
                        "tournament_name": tournament_name,
                        "tournament_id": tournament_id,
                        "phase": hm.phase_display_name,
                        "score": hm.formatted_score,
                        "result": res
                    })

                total_h2h = wins + losses + draws
                win_rate_h2h = round((wins / total_h2h) * 100, 1) if total_h2h > 0 else 0

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

                for st in shared_tournaments:
                    h2h_labels.append(st.name)

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

                    opp_entry = PlayerModel.query.filter_by(tournament_id=st.id,
                                                            global_player_id=selected_opponent_id).first()
                    opp_rank = None
                    if opp_entry:
                        ops = PlayoffStatsModel.query.filter_by(player_id=opp_entry.id).first()
                        ocs = ConsolationStatsModel.query.filter_by(player_id=opp_entry.id).first()
                        if ops and ops.final_rank is not None:
                            opp_rank = ops.final_rank
                        elif ocs and ocs.final_rank is not None:
                            opp_rank = ocs.final_rank
                    h2h_opp_ranks.append(opp_rank)

                h2h_data = {
                    "opponent": selected_opponent,
                    "wins": wins,
                    "losses": losses,
                    "draws": draws,
                    "total": total_h2h,
                    "win_rate": win_rate_h2h,
                    "history": match_history,
                    "chart_labels": h2h_labels,
                    "player_ranks": h2h_player_ranks,
                    "opp_ranks": h2h_opp_ranks
                }

        active_tab = request.args.get("tab", "obecne")

        # --- FILTROVÁNÍ A ŘAZENÍ PRO AKTIVNÍ ZÁLOŽKU ---
        tab_q = request.args.get("q", "").strip().lower()
        tab_sort_by = request.args.get("sort_by", "")
        tab_order = request.args.get("order", "desc")
        reverse_sort = (tab_order == "desc")

        if active_tab == 'turnaje':
            if not tab_sort_by: tab_sort_by = "date"
            if tab_q:
                tournaments_data = [t for t in tournaments_data if
                                    tab_q in t['tournament_name'].lower() or tab_q in str(t['rank']).lower()]

            if tab_sort_by == "name":
                tournaments_data.sort(key=lambda x: x['tournament_name'], reverse=reverse_sort)
            elif tab_sort_by == "rank":
                tournaments_data.sort(
                    key=lambda x: int(str(x['rank']).split('.')[0]) if str(x['rank']).split('.')[0].isdigit() else 999,
                    reverse=reverse_sort)
            elif tab_sort_by == "points":
                tournaments_data.sort(key=lambda x: x['points'], reverse=reverse_sort)
            else:
                tournaments_data.sort(key=lambda x: x['tournament_date'] or datetime.min.date(), reverse=reverse_sort)

        elif active_tab == 'zapasy':
            if not tab_sort_by: tab_sort_by = "tournament"
            if tab_q:
                matches_data = [m for m in matches_data if
                                tab_q in m['tournament_name'].lower() or tab_q in m['phase'].lower() or tab_q in m[
                                    'opponent_name'].lower()]

            if tab_sort_by == "phase":
                matches_data.sort(key=lambda x: x['phase'], reverse=reverse_sort)
            elif tab_sort_by == "opponent":
                matches_data.sort(key=lambda x: x['opponent_name'], reverse=reverse_sort)
            elif tab_sort_by == "score":
                matches_data.sort(key=lambda x: x['score'], reverse=reverse_sort)
            elif tab_sort_by == "result":
                matches_data.sort(key=lambda x: x['result'], reverse=reverse_sort)
            else:
                matches_data.sort(key=lambda x: x['tournament_id'] or 0, reverse=reverse_sort)

        elif active_tab == 'h2h' and h2h_data:
            if not tab_sort_by: tab_sort_by = "tournament"
            if tab_q:
                h2h_data['history'] = [hm for hm in h2h_data['history'] if
                                       tab_q in hm['tournament_name'].lower() or tab_q in hm['phase'].lower()]

            if tab_sort_by == "phase":
                h2h_data['history'].sort(key=lambda x: x['phase'], reverse=reverse_sort)
            elif tab_sort_by == "score":
                h2h_data['history'].sort(key=lambda x: x['score'], reverse=reverse_sort)
            elif tab_sort_by == "result":
                h2h_data['history'].sort(key=lambda x: x['result'], reverse=reverse_sort)
            else:
                h2h_data['history'].sort(key=lambda x: x['tournament_id'] or 0, reverse=reverse_sort)

        return {
            "player": player,
            "current_rank": current_rank,
            "win_rate": win_rate,
            "favorite_opponent": favorite_opponent,
            "nemesis": nemesis,
            "recent_form": recent_form,
            "opponents_list": opponents_list,
            "chart_labels": chart_labels,
            "chart_ranks": chart_ranks,
            "chart_points": chart_points,
            "chart_global_ranks": chart_global_ranks,
            "tournaments_data": tournaments_data,
            "matches_data": matches_data,
            "h2h_data": h2h_data,
            "active_tab": active_tab,
            "tab_q": tab_q,
            "tab_sort_by": tab_sort_by,
            "tab_order": tab_order
        }