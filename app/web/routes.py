from flask import Blueprint, render_template, request, redirect, session, send_file
from config import GROUPS_RULES, PLAYOFF_RULES
from app.services.setupwizard import SetupWizard
from app.models.models import db, Tournament as TournamentModel, Player as PlayerModel, GlobalPlayer as GlobalPlayerModel,\
    ConsolationStats as ConsolationStatsModel, PlayoffStats as PlayoffStatsModel, Match as MatchModel
from app.services.tournament import Tournament as TournamentOrchestrator
from app.services.match import evaluate, toggle_match_progress, unlock_match
from app.web.webmanager import WebManager
from app.services.queries import get_available_players_from_tournament, get_recent_finished_tournaments
from sqlalchemy import or_, and_
from sqlalchemy.orm import aliased

from models.models import Group, Bracket

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("index.html")


@main_bp.route("/settings_groups", methods=["GET", "POST"])
def settings_groups():
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    if request.method == "POST":
        action = request.form.get("action")
        print(f"DEBUG: Přišla akce: {action}")
        print(f"DEBUG: Form data: {request.form}")

        wizard.process_form_action(form_data=request.form)

        if action == "cancel":
            session.pop("wizard_data", None)
            return redirect("/")

        if action == "next":
            session["wizard_data"] = wizard.import_to_dict()
            return redirect("/settings_playoff")

        session["wizard_data"] = wizard.import_to_dict()

        # Pokud požadavek přišel přes HTMX:
        if "HX-Request" in request.headers:
            active_tournament_id = request.form.get("active_tournament_id")

            # 1. Vyrenderujeme hlavní část wizardu
            main_html = render_template(
                "partials/_wizard_content.html",
                wizard=wizard,
                GROUPS_RULES=GROUPS_RULES
            )

            # 2. Pokud byl vybraný nějaký turnaj, přibalíme aktualizované okénko hráčů (OOB swap)
            if active_tournament_id and active_tournament_id.isdigit():
                t_id = int(active_tournament_id)
                available_players = get_available_players_from_tournament(t_id, wizard)
                selected_tournament = TournamentModel.query.get(t_id)

                oob_html = f'<div id="past-players-container" hx-swap-oob="true">' \
                           f'{render_template("partials/_past_tournament_players.html", available_players=available_players, selected_tournament=selected_tournament)}' \
                           f'</div>'

                return main_html + oob_html

            return main_html

    recent_tournaments = get_recent_finished_tournaments(limit=5)

    # načteme všechna jména z GlobalPlayer pro našeptávač
    all_global_players = [g.name for g in GlobalPlayerModel.query.order_by(GlobalPlayerModel.name.asc()).all()]

    return render_template(
        "settings_groups.html",
        wizard=wizard,
        GROUPS_RULES=GROUPS_RULES,
        recent_tournaments=recent_tournaments
    )

@main_bp.route("/wizard/search-tournaments")
def search_tournaments():
    query = request.args.get("q", "").strip()

    if not query:
        tournaments = get_recent_finished_tournaments(limit=5)
    else:
        tournaments = TournamentModel.query.filter(
            TournamentModel.is_finished == True,
            TournamentModel.name.ilike(f"%{query}%")
        ).order_by(TournamentModel.date.desc()).limit(10).all()

    return render_template("partials/_past_tournaments_list.html", recent_tournaments=tournaments)

@main_bp.route("/wizard/past-tournament/<int:tournament_id>/players")
def get_past_tournament_players(tournament_id):
    """
    Routa určená pro HTMX request při kliknutí na minulý turnaj.
    Vrátí HTML partial se seznamem hráčů.
    """
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    available_players = get_available_players_from_tournament(tournament_id, wizard)
    selected_tournament = TournamentModel.query.get(tournament_id)

    return render_template(
        "partials/_past_tournament_players.html",
        available_players=available_players,
        selected_tournament=selected_tournament
    )

@main_bp.route("/settings_playoff", methods=["GET", "POST"])
def settings_playoff():
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    if request.method == "POST":
        action = request.form.get("action")
        print(f"DEBUG: Přišla akce: {action}")
        print(f"DEBUG: Form data: {request.form}")

        if action == "next":
            wizard.playoff_match_format = int(request.form.get("playoff_match_format"))
            wizard.playoff_elimination_action = request.form.get("elimination_actions")

            session["wizard_data"] = wizard.import_to_dict()

            if not wizard.check_readiness():
                return render_template(
                    "settings_playoff.html",
                    wizard=wizard,
                    PLAYOFF_RULES=PLAYOFF_RULES,
                    error="Turnaj není připraven"
                )

            # ================
            # DATABÁZE A PAMĚŤ
            # ================
            new_tournament = TournamentOrchestrator(wizard)

            session.pop("wizard_data", None)

            return redirect(f"/tournament/{new_tournament.id}/groups")

    return render_template(
        "settings_playoff.html",
        wizard=wizard,
        PLAYOFF_RULES=PLAYOFF_RULES
    )

@main_bp.route("/stats")
def stats_index():
    return redirect("/stats/tournaments")

@main_bp.route("/stats/tournaments")
def stats_tournament_view():
    # Načtení parametrů z URL (pokud nejsou, nastavíme výchozí hodnoty)
    q = request.args.get("q","").strip()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")

    # Základní dotaz - použiujeme outerjoin na PlayerModel, abychom mohli řadit podle vítěze
    query = TournamentModel.query.outerjoin(PlayerModel, TournamentModel.winner_id == PlayerModel.id)

    # 1. Vyhledávání (vyhledáváme v názvu turnaje)
    if q:
        query = query.filter(TournamentModel.name.ilike(f"%{q}%"))

    # 2. Řazení
    if sort_by == "name":
        sort_column = TournamentModel.name
    elif sort_by == "winner":
        # Zde řadíme podle jména propojeného hráče (vítěze)
        sort_column = PlayerModel.name
    elif sort_by == "total_players":
        sort_column = TournamentModel.total_players
    else:
        # Výchozí řazení
        sort_column = TournamentModel.date

    # Aplikujeme směr řazení
    if order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Spuštění dotazu a načtení výsledků
    tournaments = query.all()

    return render_template(
        "stats_tournaments.html",
        tournaments=tournaments,
        q=q,
        sort_by=sort_by,
        order=order
    )

@main_bp.route("/stats/players")
def stats_players_view():
    # Načtení parametrů z URL
    q = request.args.get("q","").strip()
    sort_by = request.args.get("sort_by", "total_points")
    order = request.args.get("order","desc")

    # Základní dotaz
    query = GlobalPlayerModel.query

    # Vyhledávání (podle jména)
    if q:
        query = query.filter(GlobalPlayerModel.name.ilike(f"%{q}%"))

    # Řazení
    if sort_by == "name":
        sort_column = GlobalPlayerModel.name
    elif sort_by == "last_points":
        sort_column = GlobalPlayerModel.last_points_gained
    elif sort_by == "matches_played":
        sort_column = GlobalPlayerModel.matches_played
    elif sort_by == "won":
        sort_column = GlobalPlayerModel.matches_won
    elif sort_by == "lost":
        sort_column = GlobalPlayerModel.matches_lost
    elif sort_by == "drawn":
        sort_column = GlobalPlayerModel.matches_drawn
    elif sort_by == "tournaments":
        sort_column = GlobalPlayerModel.tournaments_played
    elif sort_by == "last_date":
        sort_column = GlobalPlayerModel.last_tournament_date
    else:
        # Výchozí řazení
        sort_column = GlobalPlayerModel.total_points

    # Aplikujeme směr řazení
    if order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    players = query.all()

    return render_template(
        "stats_players.html",
        players=players,
        q=q,
        sort_by=sort_by,
        order=order
    )


@main_bp.route("/stats/matches")
def stats_matches_view():
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")

    PlayerA = aliased(PlayerModel)
    PlayerB = aliased(PlayerModel)
    GlobalA = aliased(GlobalPlayerModel)
    GlobalB = aliased(GlobalPlayerModel)

    # Chceme jen dokončené zápasy
    query = MatchModel.query.join(TournamentModel, MatchModel.tournament_id == TournamentModel.id) \
        .filter(MatchModel.is_finished == True)

    # Filtrujeme pryč zápasy, kde jsou oba hráči prázdní (BYE vs BYE / Neznámý vs Neznámý) ---
    query = query.filter(
        or_(MatchModel.player_a_id.isnot(None), MatchModel.player_b_id.isnot(None))
    )

    # Připojíme hráče A a B
    query = query.outerjoin(PlayerA, MatchModel.player_a_id == PlayerA.id) \
        .outerjoin(GlobalA, PlayerA.global_player_id == GlobalA.id) \
        .outerjoin(PlayerB, MatchModel.player_b_id == PlayerB.id) \
        .outerjoin(GlobalB, PlayerB.global_player_id == GlobalB.id)

    # Filtrování (vyhledávání)
    if q:
        query = query.filter(or_(
            GlobalA.name.ilike(f"%{q}%"),
            GlobalB.name.ilike(f"%{q}%"),
            TournamentModel.name.ilike(f"%{q}%")
        ))

    # Logika pro řazení
    if sort_by == "tournament":
        sort_column = TournamentModel.name
    elif sort_by == "phase":
        sort_column = MatchModel.match_type
    elif sort_by == "player_a":
        sort_column = PlayerA.name
    elif sort_by == "player_b":
        sort_column = PlayerB.name
    else:
        # Výchozí řazení (pokud nic nevybereme, nebo vybereme "date")
        sort_column = TournamentModel.date

    # Aplikování směru řazení (jako druhé pravidlo vždy přidáváme MatchModel.id, aby se zápasy ze stejného turnaje nemíchaly)
    if sort_by == "date":
        query = query.order_by(TournamentModel.date.desc(), MatchModel.id.desc())
    else:
        if order == "asc":
            query = query.order_by(sort_column.asc(), MatchModel.id.asc())
        else:
            query = query.order_by(sort_column.desc(), MatchModel.id.desc())

    matches = query.all()

    return render_template(
        "stats_matches.html",
        matches=matches,
        q=q,
        sort_by=sort_by,
        order=order
    )

@main_bp.route("/stats/match/<int:match_id>")
def stats_match_detail_view(match_id):
    match = MatchModel.query.get_or_404(match_id)
    return f"Zde se zobrazí detail Zápasu ID: {match.id}"


@main_bp.route("/stats/player/<int:player_id>")
def stats_player_detail(player_id):
    # 1. Načtení globálního hráče
    player = GlobalPlayerModel.query.get_or_404(player_id)

    # 2. Výpočet aktuálního ranku
    higher_players = GlobalPlayerModel.query.filter(GlobalPlayerModel.total_points > player.total_points).count()
    current_rank = higher_players + 1

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
            # PŘIDÁNO: Ukládáme i ID pro budoucí odkaz v HTML
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
            points = c_stats.points_gained or 0

        chart_ranks.append(rank)
        chart_points.append(points)

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
                points = c_stats.points_gained or 0

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
                "score": m.formatted_score,  # Využijeme hotovou property z modelu!
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

                    # Hledáme zápasy, kde proti sobě stál náš hráč a zvolený soupeř
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
                            tournament_id =  hm.group.tournament.id
                        elif hasattr(hm, 'bracket') and hm.bracket and hm.bracket.tournament:
                            tournament_name = hm.bracket.tournament.name
                            tournament_id = hm.bracket.tournament.id

                        match_history.append({
                            "tournament_name": tournament_name,
                            "tournament_id": tournament_id,
                            "phase":hm.phase_display_name,
                            "score": hm.formatted_score,
                            "result": res
                        })

                    total_h2h = wins + losses + draws
                    win_rate_h2h = round((wins / total_h2h) * 100, 1) if total_h2h > 0 else 0

                    # --- SPOLEČNÉ TURNAJE PRO GRAF ---
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

                        # Umístění našeho hráče
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

                        # Umístění soupeře
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
            # Filtrování
            if tab_q:
                tournaments_data = [t for t in tournaments_data if
                                    tab_q in t['tournament_name'].lower() or tab_q in str(t['rank']).lower()]

            # Řazení
            if tab_sort_by == "name":
                tournaments_data.sort(key=lambda x: x['tournament_name'], reverse=reverse_sort)
            elif tab_sort_by == "rank":
                # Ošetření textu "1. místo" na pouhé číslo 1 pro správné řazení
                tournaments_data.sort(
                    key=lambda x: int(str(x['rank']).split('.')[0]) if str(x['rank']).split('.')[0].isdigit() else 999,
                    reverse=reverse_sort)
            elif tab_sort_by == "points":
                tournaments_data.sort(key=lambda x: x['points'], reverse=reverse_sort)
            else:  # date
                tournaments_data.sort(key=lambda x: x['tournament_date'] or datetime.min.date(), reverse=reverse_sort)


        elif active_tab == 'zapasy':
            if not tab_sort_by: tab_sort_by = "tournament"
            # Filtrování
            if tab_q:
                matches_data = [m for m in matches_data if
                                tab_q in m['tournament_name'].lower() or tab_q in m['phase'].lower() or tab_q in m[
                                    'opponent_name'].lower()]

            # Řazení
            if tab_sort_by == "phase":
                matches_data.sort(key=lambda x: x['phase'], reverse=reverse_sort)
            elif tab_sort_by == "opponent":
                matches_data.sort(key=lambda x: x['opponent_name'], reverse=reverse_sort)
            elif tab_sort_by == "score":
                matches_data.sort(key=lambda x: x['score'], reverse=reverse_sort)
            elif tab_sort_by == "result":
                matches_data.sort(key=lambda x: x['result'], reverse=reverse_sort)
            else:  # tournament
                matches_data.sort(key=lambda x: x['tournament_id'] or 0, reverse=reverse_sort)

        elif active_tab == 'h2h' and h2h_data:
            if not tab_sort_by: tab_sort_by = "tournament"
            # Filtrování
            if tab_q:
                h2h_data['history'] = [hm for hm in h2h_data['history'] if
                                       tab_q in hm['tournament_name'].lower() or tab_q in hm['phase'].lower()]

            # Řazení
            if tab_sort_by == "phase":
                h2h_data['history'].sort(key=lambda x: x['phase'], reverse=reverse_sort)
            elif tab_sort_by == "score":
                h2h_data['history'].sort(key=lambda x: x['score'], reverse=reverse_sort)
            elif tab_sort_by == "result":
                h2h_data['history'].sort(key=lambda x: x['result'], reverse=reverse_sort)
            else:  # tournament
                h2h_data['history'].sort(key=lambda x: x['tournament_id'] or 0, reverse=reverse_sort)



    return render_template(
        "stats_player_detail.html",
        player=player,
        current_rank=current_rank,
        win_rate=win_rate,
        favorite_opponent=favorite_opponent,
        nemesis=nemesis,
        recent_form=recent_form,
        opponents_list=opponents_list,
        chart_labels=chart_labels,
        chart_ranks=chart_ranks,
        chart_points=chart_points,
        tournaments_data=tournaments_data,
        matches_data=matches_data,
        h2h_data=h2h_data,
        active_tab=active_tab,
        tab_q=tab_q,
        tab_sort_by=tab_sort_by,
        tab_order=tab_order
    )

@main_bp.route("/tournament/<int:tournament_id>/groups", methods=["GET", "POST"])
def groups_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = request.args.get("view") != "1"

    if request.method == "POST" and editable:
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        # Získáme navíc informaci, v jaké skupině se akce stala
        group_name = request.form.get("group_name")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.group_manager.handle_match_completion(match_id, web_manager.tournament)

        # --- ZMĚNA PRO HTMX ---
        if "HX-Request" in request.headers:
            # Načteme čerstvá data turnaje
            group_data = web_manager.get_groups_page_data()

            # Vrátíme pouze HTML fragment (tzv. partial) dané skupiny
            return render_template(
                "partials/_group_content.html",
                group_name=group_name,
                data=group_data[group_name],
                tournament=web_manager.tournament,
                editable=editable
            )

        return redirect(f"/tournament/{tournament_id}/groups")

    group_data = web_manager.get_groups_page_data()
    return render_template(
        "groups.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        editable=editable
    )


@main_bp.route("/tournament/<int:tournament_id>/playoff", methods=["GET", "POST"])
def playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = request.args.get("view") != "1"

    if request.method == "POST" and editable:
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.handle_playoff_completion(is_consolation=False)

        # --- ZMĚNA PRO HTMX ---
        if "HX-Request" in request.headers:
            # Načteme aktualizovaná data pavouka
            p_data = web_manager.get_playoff_page_data(is_consolation=False)

            return render_template(
                "partials/_playoff_content.html",
                tournament=web_manager.tournament,
                p_data=p_data,
                editable=editable
            )

        return redirect(f"/tournament/{tournament_id}/playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=False)
    return render_template(
        "playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=editable
    )


@main_bp.route("/tournament/<int:tournament_id>/consolation_minigroup", methods=["GET", "POST"])
def consolation_minigroup_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = request.args.get("view") != "1"

    if request.method == "POST" and editable:
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")
        group_name = request.form.get("group_name")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.group_manager.handle_match_completion(match_id, web_manager.tournament)

        if "HX-Request" in request.headers:
            group_data = web_manager.get_minigroup_page_data()
            return render_template(
                "partials/_group_content.html",
                group_name=group_name,
                data=group_data[group_name],
                tournament=web_manager.tournament,
                is_consolation=True,
                editable=editable
            )

        return redirect(f"/tournament/{tournament_id}/consolation_minigroup")

    group_data = web_manager.get_minigroup_page_data()
    return render_template(
        "consolation_minigroup.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        is_consolation=True,
        editable=editable
    )


@main_bp.route("/tournament/<int:tournament_id>/consolation_playoff", methods=["POST", "GET"])
def consolation_playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = request.args.get("view") != "1"

    if request.method == "POST" and editable:
        match_id = int(request.form.get("match_id", 0))
        action = request.form.get("action")

        if action == "toggle_progress":
            toggle_match_progress(match_id)
        elif action == "edit_match":
            unlock_match(match_id=match_id)
        elif action == "submit_result":
            evaluate(match_id=match_id, player_a_games=request.form.getlist("game_a[]"), player_b_games=request.form.getlist("game_b[]"))
            web_manager.handle_playoff_completion(is_consolation=True)

        if "HX-Request" in request.headers:
            p_data = web_manager.get_playoff_page_data(is_consolation=True)
            return render_template(
                "partials/_playoff_content.html",
                tournament=web_manager.tournament,
                p_data=p_data,
                editable=editable
            )

        return redirect(f"/tournament/{tournament_id}/consolation_playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=True)
    return render_template(
        "consolation_playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=editable
    )


@main_bp.route("/tournament/<int:tournament_id>/results", methods=["GET", "POST"])
def results_view(tournament_id):
    current_tournament = TournamentModel.query.get_or_404(tournament_id)
    web_manager = WebManager(tournament_id)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "download":
            file_stream = web_manager.generate_results_excel()

            safe_tournament_name = "".join(
                c for c in web_manager.tournament.name if c.isalnum() or c in (' ', '_', '-')
            ).strip().replace(' ', '_')
            filename = f"vysledky_{safe_tournament_name}.xlsx"

            return send_file(
                file_stream,
                as_attachment=True,
                download_name=filename,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        elif action == "finish_tournament":
            TournamentOrchestrator.finish_existing_tournament(tournament_id)
            return redirect(f"/tournament/{tournament_id}/results")

    # Načtení výsledků pro zobrazení v tabulce z nových tabulek PlayoffStats a ConsolationStats
    players = PlayerModel.query.filter_by(tournament_id=tournament_id).all()
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

    return render_template("results.html", tournament=current_tournament, results=results_data)


@main_bp.route("/reset_settings", methods=["POST"])
def reset_settings():
    session.pop("wizard_data", None)
    return redirect("/settings_groups")