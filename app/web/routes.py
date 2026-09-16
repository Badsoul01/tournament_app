from flask import Blueprint, render_template, request, redirect, session, send_file, make_response
from config import GROUPS_RULES, PLAYOFF_RULES
from app.services.setupwizard import SetupWizard
from app.models.models import db, Tournament as TournamentModel, Player as PlayerModel, GlobalPlayer as GlobalPlayerModel,\
    ConsolationStats as ConsolationStatsModel, PlayoffStats as PlayoffStatsModel, Match as MatchModel,\
    MatchResults as MatchResultsModel, Organizer as OrganizerModel
from app.services.tournament import Tournament as TournamentOrchestrator
from app.services.match import evaluate, toggle_match_progress, unlock_match
from app.web.webmanager import WebManager
from app.services.queries import get_available_players_from_tournament, get_recent_finished_tournaments
from sqlalchemy import or_, and_
from datetime import datetime
from app.services.stats_player_detail import PlayerStatsService

main_bp = Blueprint("main", __name__)

def can_edit_tournament(tournament):
    """Rozhodne, zda má aktuální uživatel (nebo guest) právo upravovat tento turnaj."""

    # 1. Je to přihlášený organizátor a turnaj mu patří?
    if 'organizer_id' in session and tournament.organizer_id == session['organizer_id']:
        return True

    # 2. Je to nepřihlášený "Guest", který turnaj založil v aktuální relaci?
    # Kontrolujeme, že turnaj zatím v databázi nikomu nepatří (organizer_id je None)
    if tournament.organizer_id is None and 'guest_tournaments' in session:
        if tournament.id in session['guest_tournaments']:
            return True

    # Pokud ani jedno neplatí, přístup zamítnut
    return False


@main_bp.route("/")
def home():
    active_tournaments = TournamentModel.query.filter_by(is_finished=False).order_by(TournamentModel.date.desc()).all()
    return render_template("index.html", active_tournaments=active_tournaments)


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
    q = request.args.get("q","").strip()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")

    query = TournamentModel.query.outerjoin(PlayerModel, TournamentModel.winner_id == PlayerModel.id)

    if q:
        query = query.filter(TournamentModel.name.ilike(f"%{q}%"))

    if sort_by == "name":
        sort_column = TournamentModel.name
    elif sort_by == "winner":
        sort_column = PlayerModel.name
    elif sort_by == "total_players":
        sort_column = TournamentModel.total_players
    elif sort_by == "status":
        sort_column = TournamentModel.is_finished
    else:
        sort_column = TournamentModel.date

    if order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    tournaments = query.all()

    # --- PODMÍNKA PRO HTMX ---
    if "HX-Request" in request.headers:
        return render_template(
            "stats/partials/_tournaments_table.html",
            tournaments=tournaments,
            q=q,
            sort_by=sort_by,
            order=order
        )

    return render_template(
        "stats/stats_tournaments.html",
        tournaments=tournaments,
        q=q,
        sort_by=sort_by,
        order=order
    )


@main_bp.route("/stats/tournament/<int:tournament_id>")
def stats_tournament_redirect(tournament_id):
    """Hlavní rozcestník pro turnaj ve statistikách - ve výchozím stavu hodí uživatele na skupiny."""
    return redirect(f"/stats/tournament/{tournament_id}/groups")


@main_bp.route("/stats/tournament/<int:tournament_id>/groups")
def stats_tournament_groups(tournament_id):
    web_manager = WebManager(tournament_id)
    group_data = web_manager.get_groups_page_data()

    # Zjištění, odkud uživatel přišel
    from_source = request.args.get("from")
    player_id = request.args.get("player_id")

    if from_source == "player" and player_id:
        back_url = f"/stats/player/{player_id}"
        back_label = "← Zpět na hráče"
    else:
        back_url = "/stats/tournaments"
        back_label = "← Seznam turnajů"

    return render_template(
        "groups.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        editable=False,
        prefix=f"/stats/tournament/{tournament_id}",
        base_template="stats/base_stats.html",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/playoff")
def stats_tournament_playoff(tournament_id):
    web_manager = WebManager(tournament_id)
    p_data = web_manager.get_playoff_page_data(is_consolation=False)

    # Zjištění, odkud uživatel přišel
    from_source = request.args.get("from")
    player_id = request.args.get("player_id")

    if from_source == "player" and player_id:
        back_url = f"/stats/player/{player_id}"
        back_label = "← Zpět na hráče"
    else:
        back_url = "/stats/tournaments"
        back_label = "← Seznam turnajů"

    return render_template(
        "playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=False,
        base_template="stats/base_stats.html",
        prefix=f"/stats/tournament/{tournament_id}",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/consolation_minigroup")
def stats_tournament_consolation_minigroup(tournament_id):
    web_manager = WebManager(tournament_id)
    group_data = web_manager.get_minigroup_page_data()

    # Zjištění, odkud uživatel přišel
    from_source = request.args.get("from")
    player_id = request.args.get("player_id")

    if from_source == "player" and player_id:
        back_url = f"/stats/player/{player_id}"
        back_label = "← Zpět na hráče"
    else:
        back_url = "/stats/tournaments"
        back_label = "← Seznam turnajů"

    return render_template(
        "groups.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        editable=False,
        prefix=f"/stats/tournament/{tournament_id}",
        base_template="stats/base_stats.html",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/consolation_playoff")
def stats_tournament_consolation_playoff(tournament_id):
    web_manager = WebManager(tournament_id)
    p_data = web_manager.get_playoff_page_data(is_consolation=True)

    # Zjištění, odkud uživatel přišel
    from_source = request.args.get("from")
    player_id = request.args.get("player_id")

    if from_source == "player" and player_id:
        back_url = f"/stats/player/{player_id}"
        back_label = "← Zpět na hráče"
    else:
        back_url = "/stats/tournaments"
        back_label = "← Seznam turnajů"

    return render_template(
        "consolation_playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=False,
        prefix=f"/stats/tournament/{tournament_id}",
        base_template="stats/base_stats.html",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/stats/tournament/<int:tournament_id>/results")
def stats_tournament_results(tournament_id):
    current_tournament = TournamentModel.query.get_or_404(tournament_id)
    web_manager = WebManager(tournament_id)

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

    results_data.sort(key=lambda x: x[1])

    # Zjištění, odkud uživatel přišel
    from_source = request.args.get("from")
    player_id = request.args.get("player_id")

    if from_source == "player" and player_id:
        back_url = f"/stats/player/{player_id}"
        back_label = "← Zpět na hráče"
    else:
        back_url = "/stats/tournaments"
        back_label = "← Seznam turnajů"

    return render_template(
        "results.html",
        tournament=current_tournament,
        results=results_data,
        prefix=f"/stats/tournament/{tournament_id}",
        base_template="stats/base_stats.html",
        back_url=back_url,
        back_label=back_label
    )


@main_bp.route("/auth", methods=["POST"])
def auth_route():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    tournament_id = request.form.get("tournament_id")

    if not username or not password:
        return "Jméno a heslo jsou povinné."

    organizer = OrganizerModel.query.filter_by(name=username).first()

    # KDYŽ SE PŘIHLAŠUJEME Z KONKRÉTNÍHO TURNAJE:
    if tournament_id and tournament_id.isdigit():
        if not organizer:
            return "Tento účet neexistuje."

        if not organizer.check_password(password):
            return "Nesprávné heslo."

        t_id = int(tournament_id)
        tournament = TournamentModel.query.get(t_id)

        if tournament:
            if tournament.organizer_id is not None:
                if tournament.organizer_id != organizer.id:
                    return f"Uživatel '{username}' není vlastníkem tohoto turnaje."
            else:
                guest_tournaments = session.get('guest_tournaments', [])
                if t_id not in guest_tournaments:
                    return "Tento turnaj nelze z tohoto zařízení dodatečně přihlásit."

                tournament.organizer_id = organizer.id
                db.session.commit()

    # KDYŽ SE PŘIHLAŠUJEME Z NASTAVENÍ (vytváření nového turnaje):
    else:
        if not organizer:
            organizer = OrganizerModel(name=username)
            organizer.set_password(password)
            db.session.add(organizer)
            db.session.commit()
        else:
            if not organizer.check_password(password):
                return "Nesprávné heslo."

    # Uložení do session
    session['organizer_id'] = organizer.id
    session['organizer_name'] = organizer.name
    organizer.last_login = datetime.now()
    db.session.commit()

    response = make_response()
    if tournament_id and tournament_id.isdigit():
        response.headers["HX-Redirect"] = f"/tournament/{tournament_id}/groups"
    else:
        response.headers["HX-Redirect"] = "/settings_groups"

    return response


@main_bp.route("/logout", methods=["POST"])
def logout_route():
    """Odhlášení uživatele s návratem na aktuální stránku."""
    session.pop('organizer_id', None)
    session.pop('organizer_name', None)

    # Zjistíme, odkud požadavek přišel, a vrátíme uživatele tamtéž
    referrer = request.referrer
    if referrer:
        return redirect(referrer)

    # Fallback, pokud by referrer chyběl
    return redirect("/settings_groups")

@main_bp.route("/stats/tournament/<int:tournament_id>/details")
def stats_tournament_details(tournament_id):
    tournament = TournamentModel.query.get_or_404(tournament_id)

    top_players = db.session.query(PlayerModel, PlayoffStatsModel.final_rank)\
        .join(PlayoffStatsModel, PlayerModel.id == PlayoffStatsModel.player_id)\
        .filter(PlayerModel.tournament_id == tournament_id, PlayoffStatsModel.final_rank <= 3)\
        .order_by(PlayoffStatsModel.final_rank.asc())\
        .all()

    # Ukládáme jméno i globální ID pro proklik na profil
    top_3 = {}
    for player, rank in top_players:
        top_3[rank] = {
            "name": player.name,
            "global_id": player.global_player_id
        }

    return render_template("stats/partials/_tournament_details_row.html", tournament=tournament, top_3=top_3)

@main_bp.route("/stats/players")
def stats_players_view():
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "total_points")
    order = request.args.get("order", "desc")

    # Načteme všechny hráče z DB
    players = GlobalPlayerModel.query.all()

    # Případné vyhledávání podle jména
    if q:
        players = [p for p in players if q.lower() in p.name.lower()]

    # Celkový žebříček pro výpočet pozice (ranku) každého hráče
    all_players_sorted = GlobalPlayerModel.query.all()
    all_players_sorted.sort(key=lambda p: p.total_points, reverse=True)
    ranks_map = {p.id: idx + 1 for idx, p in enumerate(all_players_sorted)}

    # Řazení aktuálně zobrazeného seznamu podle zvoleného sloupce
    reverse_sort = (order == "desc")
    if sort_by == "name":
        players.sort(key=lambda p: p.name, reverse=reverse_sort)
    else:
        players.sort(key=lambda p: p.total_points, reverse=reverse_sort)

    # --- PODMÍNKA PRO HTMX ---
    if "HX-Request" in request.headers:
        return render_template(
            "/stats/partials/_players_table.html",
            players=players,
            ranks_map=ranks_map,
            q=q,
            sort_by=sort_by,
            order=order
        )

    return render_template(
        "/stats/stats_players.html",
        players=players,
        ranks_map=ranks_map,
        q=q,
        sort_by=sort_by,
        order=order
    )


@main_bp.route("/stats/matches")
def stats_matches_view():
    q = request.args.get("q", "").strip().lower()
    sort_by = request.args.get("sort_by", "date")
    order = request.args.get("order", "desc")

    # 1. Načteme hotové zápasy spojené s turnaji z databáze
    query = MatchModel.query.join(TournamentModel, MatchModel.tournament_id == TournamentModel.id) \
        .filter(MatchModel.is_finished == True)

    query = query.filter(
        or_(MatchModel.player_a_id.isnot(None), MatchModel.player_b_id.isnot(None))
    )

    # Základní řazení z DB
    if sort_by == "tournament":
        query = query.order_by(TournamentModel.name.asc() if order == "asc" else TournamentModel.name.desc())
    else:
        query = query.order_by(TournamentModel.date.desc(), MatchModel.id.desc())

    matches = query.all()

    # 2. Filtrování v Pythonu (stejně jako v detailu hráče), které vidí i české názvy fází
    if q:
        filtered_matches = []
        for m in matches:
            p_a_name = m.player_a.name.lower() if m.player_a else ""
            p_b_name = m.player_b.name.lower() if m.player_b else ""
            t_name = m.tournament.name.lower() if m.tournament else ""
            phase_name = m.phase_display_name.lower() if hasattr(m, 'phase_display_name') else ""

            # Pokud hledaný výraz odpovídá hráči, turnaji nebo fázi (např. "útěcha-minitabulka")
            if q in p_a_name or q in p_b_name or q in t_name or q in phase_name:
                filtered_matches.append(m)
        matches = filtered_matches

    # --- PODMÍNKA PRO HTMX ---
    if "HX-Request" in request.headers:
        return render_template(
            "stats/partials/_matches_table.html",
            matches=matches,
            q=q,
            sort_by=sort_by,
            order=order
        )

    return render_template(
        "stats/stats_matches.html",
        matches=matches,
        q=q,
        sort_by=sort_by,
        order=order
    )


@main_bp.route("/stats/match/<int:match_id>")
def stats_match_detail_view(match_id):
    match = MatchModel.query.get_or_404(match_id)

    # 1. Sety zápasu
    sets = match.sets.order_by(MatchResultsModel.set_number).all() if hasattr(match, 'sets') else []

    # 2. Úspěšnost hráčů (Win Rate) v celkovém měřítku
    def get_player_stats(player):
        if not player or not player.global_profile:
            return {"wins": 0, "losses": 0, "win_rate": 0}
        gp = player.global_profile
        played = gp.matches_played or 0
        won = gp.matches_won or 0
        rate = round((won / played) * 100, 1) if played > 0 else 0
        return {"wins": won, "losses": gp.matches_lost or 0, "win_rate": rate}

    stats_a = get_player_stats(match.player_a)
    stats_b = get_player_stats(match.player_b)

    # 3. Vzájemná H2H bilance před tímto zápasem
    h2h_wins_a = 0
    h2h_wins_b = 0
    h2h_draws = 0

    if match.player_a and match.player_b and match.player_a.global_player_id and match.player_b.global_player_id:
        g_id_a = match.player_a.global_player_id
        g_id_b = match.player_b.global_player_id

        loc_ids_a = [p.id for p in PlayerModel.query.filter_by(global_player_id=g_id_a).all()]
        loc_ids_b = [p.id for p in PlayerModel.query.filter_by(global_player_id=g_id_b).all()]

        # Hledáme všechny dřívější nebo současné vzájemné zápasy do ID tohoto zápasu
        past_matches = MatchModel.query.filter(
            or_(
                and_(MatchModel.player_a_id.in_(loc_ids_a), MatchModel.player_b_id.in_(loc_ids_b)),
                and_(MatchModel.player_a_id.in_(loc_ids_b), MatchModel.player_b_id.in_(loc_ids_a))
            ),
            MatchModel.is_finished == True,
            MatchModel.id <= match.id  # Včetně tohoto zápasu, nebo můžeme dát < pro stav před ním
        ).all()

        for pm in past_matches:
            is_a_in_a = pm.player_a_id in loc_ids_a
            our_id = pm.player_a_id if is_a_in_a else pm.player_b_id

            if pm.winner_id is None:
                h2h_draws += 1
            elif pm.winner_id == our_id:
                h2h_wins_a += 1
            else:
                h2h_wins_b += 1

    h2h_data = {
        "wins_a": h2h_wins_a,
        "wins_b": h2h_wins_b,
        "draws": h2h_draws,
        "total": h2h_wins_a + h2h_wins_b + h2h_draws
    }

    return render_template(
        "stats/partials/_match_details_row.html",
        match=match,
        sets=sets,
        stats_a=stats_a,
        stats_b=stats_b,
        h2h_data=h2h_data
    )


@main_bp.route("/stats/player/<int:player_id>")
def stats_player_detail(player_id):
    # Získáme veškerá data ze servisní vrstvy
    context = PlayerStatsService.get_player_profile_data(player_id, request.args)

    active_tab = context.get("active_tab", "obecne")

    # Podpora pro HTMX – pokud jde o AJAX požadavek pro konkrétní záložku
    if request.headers.get("HX-Request"):
        template_map = {
            'obecne': 'stats/partials/_tab_player_overall.html',
            'turnaje': 'stats/partials/_tab_player_tournaments.html',
            'zapasy': 'stats/partials/_tab_player_matches.html',
            'h2h': 'stats/partials/_tab_player_h2h.html',
        }
        return render_template(template_map.get(active_tab, 'stats/partials/_tab_player_overall.html'), **context)

    # Klasické načtení celé stránky
    return render_template("stats/stats_player_detail.html", **context)

@main_bp.route("/tournament/<int:tournament_id>/groups", methods=["GET", "POST"])
def groups_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = can_edit_tournament(web_manager.tournament)

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
                editable=editable,
                prefix=f"/tournament/{tournament_id}",
                base_template="base_tournament.html"
            )

        return redirect(f"/tournament/{tournament_id}/groups")

    group_data = web_manager.get_groups_page_data()
    return render_template(
        "groups.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        editable=editable,
        prefix=f"/tournament/{tournament_id}",
        base_template="base_tournament.html"
    )


@main_bp.route("/tournament/<int:tournament_id>/playoff", methods=["GET", "POST"])
def playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = can_edit_tournament(web_manager.tournament)

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
        editable=editable,
        prefix = f"/tournament/{tournament_id}",
        base_template = "base_tournament.html"
    )


@main_bp.route("/tournament/<int:tournament_id>/consolation_minigroup", methods=["GET", "POST"])
def consolation_minigroup_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = can_edit_tournament(web_manager.tournament)

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
                editable=editable,
                prefix=f"/tournament/{tournament_id}",
                base_template="base_tournament.html"
            )

        return redirect(f"/tournament/{tournament_id}/consolation_minigroup")

    group_data = web_manager.get_minigroup_page_data()
    return render_template(
        "consolation_minigroup.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        is_consolation=True,
        editable=editable,
        prefix=f"/tournament/{tournament_id}",
        base_template="base_tournament.html"
    )


@main_bp.route("/tournament/<int:tournament_id>/consolation_playoff", methods=["POST", "GET"])
def consolation_playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)

    editable = can_edit_tournament(web_manager.tournament)

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
                editable=editable,
                prefix=f"/tournament/{tournament_id}",
                base_template="base_tournament.html"
            )

        return redirect(f"/tournament/{tournament_id}/consolation_playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=True)
    return render_template(
        "consolation_playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=editable,
        prefix=f"/tournament/{tournament_id}",
        base_template="base_tournament.html"
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

    return render_template(
        "results.html",
        tournament=current_tournament,
        results=results_data,
        prefix=f"/tournament/{tournament_id}",
        base_template="base_tournament.html"
    )


@main_bp.route("/reset_settings", methods=["POST"])
def reset_settings():
    session.pop("wizard_data", None)
    return redirect("/settings_groups")