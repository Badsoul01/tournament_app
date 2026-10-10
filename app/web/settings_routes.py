from flask import make_response, render_template, request, redirect, session
from urllib.parse import quote
import json

from services.tournament.tournament_management import TournamentManagementService
from .blueprint import main_bp
from config import GROUPS_RULES, PLAYOFF_RULES
from app.services.tournament.setupwizard import SetupWizard
from app.models.models import Tournament as TournamentModel, GlobalPlayer as GlobalPlayerModel, \
    Player as PlayerModel
from app.services.tournament.tournament import Tournament as TournamentOrchestrator
from app.services.utils.queries import get_available_players_from_tournament, get_recent_finished_tournaments

@main_bp.route("/tournament_settings", methods=["GET", "POST"])
def tournament_settings():
    wizard = SetupWizard()
    if "wizard_data" in session:
        wizard.import_from_dict(session["wizard_data"])

    if request.method == "POST":
        action = request.form.get("action")

        action_result =  wizard.process_form_action(
            form_data=request.form
        )

        group_structure_actions = (
            "increase_groups",
            "decrease_groups",
            "remove_single_group",
            "reset_all_groups",
        )



        if action == "cancel":
            session.pop("wizard_data", None)
            return redirect("/")

        if action == "next":
            session["wizard_data"] = wizard.import_to_dict()

            if not wizard.check_readiness():
                recent_tournaments = get_recent_finished_tournaments(limit=5)

                all_global_players = [
                    g.name
                    for g in GlobalPlayerModel.query
                    .order_by(GlobalPlayerModel.name.asc())
                    .all()
                ]

                return render_template(
                    "settings/tournament_settings.html",
                    wizard=wizard,
                    GROUPS_RULES=GROUPS_RULES,
                    PLAYOFF_RULES=PLAYOFF_RULES,
                    recent_tournaments=recent_tournaments,
                    all_global_players=all_global_players,
                    error="Turnaj není připraven"
                )

            editing_tournament_id = session.get("editing_tournament_id")

            if editing_tournament_id:
                management = TournamentManagementService(
                    tournament_id=editing_tournament_id,
                    organizer_id=session.get("organizer_id")
                )

                if not management.rebuild_tournamnet(wizard):
                    return "Turnaj nelze upravit.", 403

                tournament_id = editing_tournament_id

            else:
                new_tournament = TournamentOrchestrator(wizard)
                tournament_id = new_tournament.id



            session.pop("wizard_data", None)
            session.pop("editing_tournament_id", None)

            return redirect(
                f"/tournament/{tournament_id}/groups"
            )

        session["wizard_data"] = wizard.import_to_dict()

        # Pokud požadavek přišel přes HTMX:
        if "HX-Request" in request.headers:

            if action == "update_base_settings":
                base_html = render_template(
                    "settings/partials/_base_settings.html",
                    wizard=wizard,
                    GROUPS_RULES=GROUPS_RULES
                )

                button_html = (
                        '<div id="wizard-button-container" hx-swap-oob="true">'
                        + render_template(
                    "settings/partials/_wizard_button.html",
                    wizard=wizard
                )
                        + "</div>"
                )

                return base_html + button_html

            if action in (
                    "update_group_settings",
                    "update_playoff_settings"
            ):
                rules_html = render_template(
                    "settings/partials/_rules_settings.html",
                    wizard=wizard,
                    GROUPS_RULES=GROUPS_RULES,
                    PLAYOFF_RULES=PLAYOFF_RULES
                )

                button_html = (
                        '<div id="wizard-button-container" hx-swap-oob="true">'
                        + render_template(
                    "settings/partials/_wizard_button.html",
                    wizard=wizard
                )
                        + "</div>"
                )

                return rules_html + button_html

            active_tournament_id = request.form.get(
                "active_tournament_id"
            )

            main_html = render_template(
                "settings/partials/_wizard_content.html",
                wizard=wizard,
                GROUPS_RULES=GROUPS_RULES
            )
            button_html = (
                    '<div id="wizard-button-container" hx-swap-oob="true">'
                    + render_template(
                "settings/partials/_wizard_button.html",
                wizard=wizard
            )
                    + "</div>"
            )

            if action == "scrap_players":

                message_parts = []
                if action_result:
                    if action_result["name"]:
                        message_parts.append(
                            f"Název: {action_result['name']}"
                        )

                    if action_result["location"]:
                        message_parts.append(
                            f"Lokace: {action_result['location']}"
                        )

                    message_parts.append(
                         f"Hráči: +{action_result['players_added']}"
                    )


                base_html = (
                        '<div id="base-settings-container" hx-swap-oob="true">'
                        + render_template(
                    "settings/partials/_base_settings.html",
                    wizard=wizard,
                    GROUPS_RULES=GROUPS_RULES
                )
                        + "</div>"
                )

                response = make_response(
                    main_html + base_html + button_html
                )

                response.headers["HX-Trigger"] = json.dumps({
                    "showToast": quote(" • ".join(message_parts))
                })

                return response

            if action in group_structure_actions:
                rules_html = (
                        '<div id="rules-settings-container" hx-swap-oob="true">'
                        + render_template(
                    "settings/partials/_rules_settings.html",
                    wizard=wizard,
                    GROUPS_RULES=GROUPS_RULES,
                    PLAYOFF_RULES=PLAYOFF_RULES
                )
                        + "</div>"
                )

                return main_html + rules_html + button_html


            if (
                    active_tournament_id
                    and active_tournament_id.isdigit()
            ):
                t_id = int(active_tournament_id)

                available_players = (
                    get_available_players_from_tournament(
                        t_id,
                        wizard
                    )
                )

                selected_tournament = (
                    TournamentModel.query.get(t_id)
                )

                def get_tournament_rank(player):
                    if (
                            getattr(player, "playoff_stats", None)
                            and player.playoff_stats.final_rank is not None
                    ):
                        return player.playoff_stats.final_rank

                    if (
                            getattr(player, "consolation_stats", None)
                            and player.consolation_stats.final_rank is not None
                    ):
                        return player.consolation_stats.final_rank

                    return float("inf")

                available_players.sort(
                    key=get_tournament_rank
                )

                oob_html = (
                        '<div id="past-players-container" '
                        'hx-swap-oob="true">'
                        + render_template(
                    "settings/partials/"
                    "_past_tournament_players.html",
                    available_players=available_players,
                    selected_tournament=selected_tournament
                )
                        + "</div>"
                )

                return main_html + oob_html + button_html



            return main_html + button_html

    recent_tournaments = get_recent_finished_tournaments(limit=5)

    # načteme všechna jména z GlobalPlayer pro našeptávač
    all_global_players = [g.name for g in GlobalPlayerModel.query.order_by(GlobalPlayerModel.name.asc()).all()]

    return render_template(
        "settings/tournament_settings.html",
        wizard=wizard,
        GROUPS_RULES=GROUPS_RULES,
        PLAYOFF_RULES=PLAYOFF_RULES,
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

@main_bp.route("/reset_settings", methods=["POST"])
def reset_settings():
    session.pop("wizard_data", None)
    session.pop("editing_tournament_id", None)

    return redirect("/tournament_settings")