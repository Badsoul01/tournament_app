from flask import request, redirect, session, make_response
from datetime import datetime

from .blueprint import main_bp
from app.models.models import db, Tournament as TournamentModel, Organizer as OrganizerModel

@main_bp.route("/auth", methods=["POST"])
def auth_route():
    # Převedeme uživatelské jméno na malé písmena a ořízneme mezery
    username = request.form.get("username", "").strip().lower()
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