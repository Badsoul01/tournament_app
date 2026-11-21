"""22.9A LAB ONLY: shared revision for existing online result POSTs.

Fail-closed: only local unix socket and offline_sync_lab226b; use copied DB only.
No protection for legacy routes outside four match entry points; NOT FOR VPS.
"""
import os
from uuid import uuid4
from sqlalchemy import text
from flask import abort
from app.models.models import db, Match as MatchModel
from app.services.utils.transaction import atomic_sync_update

TARGET = "offline_sync_lab226b"

def lab_enabled():
    return os.environ.get("LAB229_ENABLE") == "1"

def verify_isolation():
    # Checked before EACH write, not just at startup.
    with db.engine.connect() as conn:
        dbname, server = conn.execute(text(
            "SELECT current_database(), inet_server_addr()"
        )).one()
    if dbname != TARGET or server is not None:
        raise RuntimeError("LAB229 SAFETY STOP: local isolated PostgreSQL clone required")

def submit_online(web_manager, form_data, *, is_playoff=False, is_consolation=False):
    if not lab_enabled():
        return web_manager.process_match_action(form_data, is_playoff=is_playoff, is_consolation=is_consolation)
    verify_isolation()
    # All three existing match POST actions modify the database.
    action = form_data.get("action")
    if action not in ("toggle_progress", "edit_match", "submit_result"):
        abort(409, description="LAB229: unsupported match action")
    try:
        match_id = int(form_data.get("match_id", 0))
    except (TypeError, ValueError):
        abort(400)
    if match_id <= 0:
        abort(400)
    tid = web_manager.tournament_id
    with atomic_sync_update():
        # Lock the tournament, serializing all lab online/offline writes.
        db.session.execute(text("SELECT id FROM public.tournaments WHERE id=:tid FOR UPDATE"), {"tid": tid}).scalar_one()
        match = db.session.get(MatchModel, match_id)
        if match is None or match.tournament_id != tid:
            abort(409, description="LAB229: match missing or belongs elsewhere")
        # A finished match may be unlocked for correction, but must not
        # silently accept a second submit_result without that step.
        if action == "submit_result" and match.is_finished:
            abort(409, description="LAB229: unlock finished match before submitting a correction")
        # Deliberately use the SAME tables as lab229 offline gateway (to be integrated next).
        state = db.session.execute(text(
            "SELECT revision FROM public.lab229_state WHERE tournament_id=:tid FOR UPDATE"
        ), {"tid": tid}).scalar_one_or_none()
        if state is None:
            abort(409, description="LAB229: initialize lab229_state before writes")
        web_manager.process_match_action(form_data, is_playoff=is_playoff, is_consolation=is_consolation)
        db.session.execute(text(
            "UPDATE public.lab229_state SET revision=revision+1 WHERE tournament_id=:tid"
        ), {"tid": tid})
        db.session.execute(text(
            "INSERT INTO public.lab229_requests(request_id,tournament_id,revision,origin) "
            "VALUES (:rid,:tid,:revision,'online')"
        ), {"rid": str(uuid4()), "tid": tid, "revision": state+1})
