from flask import render_template, request, redirect, send_file
from app.services.tournament import Tournament as TournamentOrchestrator
from app.web.webmanager import WebManager
from . import main_bp
from app.services.permission import can_edit_tournament
from app.services.export import TournamentExportService

@main_bp.route("/tournament/<int:tournament_id>/groups", methods=["GET", "POST"])
def groups_view(tournament_id):
    web_manager = WebManager(tournament_id)
    editable = can_edit_tournament(web_manager.tournament)

    if request.method == "POST" and editable:
        web_manager.process_match_action(request.form, is_playoff=False)

        if "HX-Request" in request.headers:
            group_name = request.form.get("group_name")
            group_data = web_manager.get_groups_page_data()
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
        web_manager.process_match_action(request.form, is_playoff=True, is_consolation=False)

        if "HX-Request" in request.headers:
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
        prefix=f"/tournament/{tournament_id}",
        base_template="base_tournament.html"
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
        web_manager.process_match_action(request.form, is_playoff=True, is_consolation=True)

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
            return redirect(f"/tournament/{tournament_id}/results")

    # Získání dat přes WebManager místo přímého dotazování v routě
    results_data = web_manager.get_results_data()

    return render_template(
        "results.html",
        tournament=web_manager.tournament,
        results=results_data,
        prefix=f"/tournament/{tournament_id}",
        base_template="base_tournament.html"
    )

