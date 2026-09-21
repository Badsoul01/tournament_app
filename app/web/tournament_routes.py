from urllib.parse import quote
from flask import render_template, request, redirect, send_file, make_response
from app.services.tournament.tournament import Tournament as TournamentOrchestrator
from app.web.webmanager import WebManager
from . import main_bp
from app.services.utils.permission import can_edit_tournament
from app.services.utils.export import TournamentExportService
from app.models.models import  Match as MatchModel

@main_bp.route("/tournament/<int:tournament_id>/groups", methods=["GET", "POST"])
def groups_view(tournament_id):
    web_manager = WebManager(tournament_id)
    editable = can_edit_tournament(web_manager.tournament)

    if request.method == "POST" and editable:
        web_manager.process_match_action(request.form, is_playoff=False)

        if "HX-Request" in request.headers:
            group_name = request.form.get("group_name")
            group_data = web_manager.get_groups_page_data()
            response = make_response(render_template(
                "tournament/partials/_group_content.html",
                group_name=group_name,
                data=group_data[group_name],
                tournament=web_manager.tournament,
                editable=editable,
                prefix=f"/tournament/{tournament_id}",
                base_template="tournament/base_tournament.html"
            ))

            if request.form.get("action") == "submit_result":
                msg = quote("Výsledek zápasu byl přidán do kroniky!")
                response.headers["HX-Trigger"] = f'{{"showToast": "{msg}"}}'

            return response

        return redirect(f"/tournament/{tournament_id}/groups")

    group_data = web_manager.get_groups_page_data()
    return render_template(
        "tournament/groups.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        editable=editable,
        prefix=f"/tournament/{tournament_id}",
        base_template="tournament/base_tournament.html"
    )


@main_bp.route("/tournament/<int:tournament_id>/playoff", methods=["GET", "POST"])
def playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)
    editable = can_edit_tournament(web_manager.tournament)

    if request.method == "POST" and editable:
        web_manager.process_match_action(request.form, is_playoff=True, is_consolation=False)

        if "HX-Request" in request.headers:
            p_data = web_manager.get_playoff_page_data(is_consolation=False)
            response = make_response(render_template(
                "tournament/partials/_playoff_content.html",
                tournament=web_manager.tournament,
                p_data=p_data,
                editable=editable,
                prefix=f"/tournament/{tournament_id}",
                base_template="tournament/base_tournament.html"
            ))

            if request.form.get("action") == "submit_result":
                msg = quote("Výsledek zápasu byl přidán do kroniky!")
                response.headers["HX-Trigger"] = f'{{"showToast": "{msg}"}}'

            return response

        return redirect(f"/tournament/{tournament_id}/playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=False)
    return render_template(
        "tournament/playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=editable,
        prefix=f"/tournament/{tournament_id}",
        base_template="tournament/base_tournament.html"
    )


@main_bp.route("/tournament/<int:tournament_id>/consolation_minigroup", methods=["GET", "POST"])
def consolation_minigroup_view(tournament_id):
    web_manager = WebManager(tournament_id)
    editable = can_edit_tournament(web_manager.tournament)

    if request.method == "POST" and editable:
        web_manager.process_match_action(request.form, is_playoff=False)

        if "HX-Request" in request.headers:
            group_name = request.form.get("group_name")
            group_data = web_manager.get_minigroup_page_data()
            response = make_response(render_template(
                "tournament/partials/_group_content.html",
                group_name=group_name,
                data=group_data[group_name],
                tournament=web_manager.tournament,
                is_consolation=True,
                editable=editable,
                prefix=f"/tournament/{tournament_id}",
                base_template="tournament/base_tournament.html"
            ))

            if request.form.get("action") == "submit_result":
                msg = quote("Výsledek zápasu byl přidán do kroniky!")
                response.headers["HX-Trigger"] = f'{{"showToast": "{msg}"}}'

            return response

        return redirect(f"/tournament/{tournament_id}/consolation_minigroup")

    group_data = web_manager.get_minigroup_page_data()
    return render_template(
        "tournament/consolation_minigroup.html",
        tournament=web_manager.tournament,
        group_data=group_data,
        is_consolation=True,
        editable=editable,
        prefix=f"/tournament/{tournament_id}",
        base_template="tournament/base_tournament.html"
    )


@main_bp.route("/tournament/<int:tournament_id>/consolation_playoff", methods=["POST", "GET"])
def consolation_playoff_view(tournament_id):
    web_manager = WebManager(tournament_id)
    editable = can_edit_tournament(web_manager.tournament)

    if request.method == "POST" and editable:
        web_manager.process_match_action(request.form, is_playoff=True, is_consolation=True)

        if "HX-Request" in request.headers:
            p_data = web_manager.get_playoff_page_data(is_consolation=True)
            response = make_response(render_template(
                "tournament/partials/_playoff_content.html",
                tournament=web_manager.tournament,
                p_data=p_data,
                editable=editable,
                prefix=f"/tournament/{tournament_id}",
                base_template="tournament/base_tournament.html"
            ))

            if request.form.get("action") == "submit_result":
                msg = quote("Výsledek zápasu byl přidán do kroniky!")
                response.headers["HX-Trigger"] = f'{{"showToast": "{msg}"}}'

            return response
        return redirect(f"/tournament/{tournament_id}/consolation_playoff")

    p_data = web_manager.get_playoff_page_data(is_consolation=True)
    return render_template(
        "tournament/consolation_playoff.html",
        tournament=web_manager.tournament,
        p_data=p_data,
        editable=editable,
        prefix=f"/tournament/{tournament_id}",
        base_template="tournament/base_tournament.html"
    )


@main_bp.route("/tournament/<int:tournament_id>/results", methods=["GET", "POST"])
def results_view(tournament_id):
    web_manager = WebManager(tournament_id)
    editable = can_edit_tournament(web_manager.tournament)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "download":
            file_stream = TournamentExportService.generate_results_excel(tournament_id)

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

        elif action == "finish_tournament" and editable:
            TournamentOrchestrator.finish_existing_tournament(tournament_id)
            return redirect(
                f"/tournament/<int:tournament_id>/results".replace("<int:tournament_id>", str(tournament_id)))

    results_data = web_manager.get_results_data()

    unfinished_matches = MatchModel.query.filter_by(tournament_id=tournament_id, is_finished=False).all()
    has_real_unfinished = any(m.player_a_id is not None and m.player_b_id is not None for m in unfinished_matches)
    can_finish = not has_real_unfinished and not web_manager.tournament.is_finished

    return render_template(
        "tournament/results.html",
        tournament=web_manager.tournament,
        results=results_data,
        can_finish=can_finish,
        editable=editable,
        is_management=True,
        prefix=f"/tournament/{tournament_id}",
        base_template="tournament/base_tournament.html"
    )