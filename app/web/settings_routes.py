from flask import render_template, request, redirect, session
from .blueprint import main_bp
from config import GROUPS_RULES, PLAYOFF_RULES
from app.services.tournament.setupwizard import SetupWizard
from app.models.models import Tournament as TournamentModel, GlobalPlayer as GlobalPlayerModel, \
    Player as PlayerModel
from app.services.tournament.tournament import Tournament as TournamentOrchestrator
from app.services.utils.queries import get_available_players_from_tournament, get_recent_finished_tournaments

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

            # 1. Vyrenderujeme hlavní část wizardu (aktualizovaná cesta k partials ve složce settings)
            main_html = render_template(
                "settings/partials/_wizard_content.html",
                wizard=wizard,
                GROUPS_RULES=GROUPS_RULES
            )

            # 2. Pokud byl vybraný nějaký turnaj, přibalíme aktualizované okénko hráčů (OOB swap)
            if active_tournament_id and active_tournament_id.isdigit():
                t_id = int(active_tournament_id)
                available_players = get_available_players_from_tournament(t_id, wizard)
                selected_tournament = TournamentModel.query.get(t_id)

                # PŘIDÁNO: Seřazení hráčů podle konečného ranku i po odeslání akce
                def get_tournament_rank(player):
                    if getattr(player, 'playoff_stats', None) and player.playoff_stats.final_rank is not None:
                        return player.playoff_stats.final_rank
                    if getattr(player, 'consolation_stats', None) and player.consolation_stats.final_rank is not None:
                        return player.consolation_stats.final_rank
                    return float('inf')

                available_players.sort(key=get_tournament_rank)

                oob_html = f'<div id="past-players-container" hx-swap-oob="true">' \
                           f'{render_template("settings/partials/_past_tournament_players.html", available_players=available_players, selected_tournament=selected_tournament)}' \
                           f'</div>'

                return main_html + oob_html

            return main_html

    recent_tournaments = get_recent_finished_tournaments(limit=5)

    # načteme všechna jména z GlobalPlayer pro našeptávač
    all_global_players = [g.name for g in GlobalPlayerModel.query.order_by(GlobalPlayerModel.name.asc()).all()]

    return render_template(
        "settings/settings_groups.html",
        wizard=wizard,
        GROUPS_RULES=GROUPS_RULES,
        recent_tournaments=recent_tournaments,
        all_global_players=all_global_players
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

    return render_template("settings/partials/_past_tournaments_list.html", recent_tournaments=tournaments)


@main_bp.route("/wizard/past-tournament/<int:tournament_id>/players")
def get_past_tournament_players(tournament_id):
    """
    Routa určená pro HTMX request při kliknutí na minulý turnaj.
    Vrátí HTML partial se seznamem hráčů a obarví vybraný turnaj.
    """
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    available_players = get_available_players_from_tournament(tournament_id, wizard)
    selected_tournament = TournamentModel.query.get(tournament_id)

    # available_players je seznam stringů (jmen). Potřebujeme zjistit jejich rank v DB.
    # Abychom nedělali query v cyklu, načteme si všechny hráče pro daný turnaj najednou
    db_players = PlayerModel.query.filter_by(tournament_id=tournament_id).all()
    # Vytvoříme si slovník: jméno -> rank
    rank_map = {}
    for p in db_players:
        rank = float('inf')
        if p.playoff_stats and p.playoff_stats.final_rank is not None:
            rank = p.playoff_stats.final_rank
        elif p.consolation_stats and p.consolation_stats.final_rank is not None:
            rank = p.consolation_stats.final_rank
        rank_map[p.name] = rank

        # available_players je seznam stringů (jmen). Načteme si jejich objekty z DB a zjistíme rank.
        db_players = PlayerModel.query.filter_by(tournament_id=tournament_id).all()
        rank_map = {}
        for p in db_players:
            rank = float('inf')
            if p.playoff_stats and p.playoff_stats.final_rank is not None:
                rank = p.playoff_stats.final_rank
            elif p.consolation_stats and p.consolation_stats.final_rank is not None:
                rank = p.consolation_stats.final_rank
            rank_map[p.name] = rank

        # Seřadíme pole stringů
        available_players.sort(key=lambda name: rank_map.get(name, float('inf')))
    # 2. Vyrenderujeme seznam hráčů pro pravý sloupec
    html_response = render_template(
        "settings/partials/_past_tournament_players.html",
        available_players=available_players,
        selected_tournament=selected_tournament
    )

    # 3. Mini skript, který se provede po načtení a obarví vybraný turnaj vlevo
    # (Odstraní zvýraznění všem a přidá ho jen tomu nakliknutému)
    script = f"""
    <script>
        document.querySelectorAll('.tournament-list-link').forEach(link => {{
            link.classList.remove('active-tournament-link');
        }});
        var activeLink = document.querySelector('a[hx-get="/wizard/past-tournament/{tournament_id}/players"]');
        if(activeLink) {{
            activeLink.classList.add('active-tournament-link');
        }}
    </script>
    """

    return html_response + script


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
                    "settings/settings_playoff.html",
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
        "settings/settings_playoff.html",
        wizard=wizard,
        PLAYOFF_RULES=PLAYOFF_RULES
    )

@main_bp.route("/reset_settings", methods=["POST"])
def reset_settings():
    session.pop("wizard_data", None)
    return redirect("/settings_groups")