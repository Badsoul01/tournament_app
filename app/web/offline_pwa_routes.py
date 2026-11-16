"""Staging-only, isolated offline PWA at /offline/.

Register from create_app() exclusively when OFFLINE_SYNC_STAGING=1.
Never expose arbitrary project files; only the approved Python engine modules.
"""
from pathlib import Path
from flask import Blueprint, current_app, abort, send_from_directory

offline_pwa_bp = Blueprint("offline_pwa", __name__, url_prefix="/offline")

# Public Python source files that are already executed in the browser by Pyodide.
# Never add configuration, credentials, .env, or other server-only modules here.
ENGINE_ALLOWLIST = frozenset({
    "app/models/models.py",
    "app/services/utils/transaction.py",
    "app/services/utils/player.py",
    "app/services/utils/match.py",
    "app/services/tournament/groupmanager.py",
    "app/services/tournament/playoff.py",
    "app/services/tournament/seedingengine.py",
    "app/services/tournament/tournament.py",
    "app/web/webmanager.py",
})


def _asset_dir():
    return Path(current_app.static_folder) / "offline"


@offline_pwa_bp.get("/")
def offline_home():
    response = send_from_directory(_asset_dir(), "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@offline_pwa_bp.get("/groups")
@offline_pwa_bp.get("/playoff")
@offline_pwa_bp.get("/consolation")
@offline_pwa_bp.get("/results")
def offline_phase_page():
    # Shared shell: each view reads the same IndexedDB SQLite.
    response = send_from_directory(_asset_dir(), "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@offline_pwa_bp.get("/engine/<path:module>")
def offline_python_module(module):
    if module not in ENGINE_ALLOWLIST:
        abort(404)
    # current_app.root_path points to the package's app/ directory.
    project_root = Path(current_app.root_path).parent
    response = send_from_directory(project_root, module, mimetype="text/x-python")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@offline_pwa_bp.get("/<path:filename>")
def offline_asset(filename):
    # Only direct files in app/static/offline; disallow subdirectories, .env etc.
    if '/' in filename or filename.startswith('.') or filename not in {
        'index.html', 'app.js', 'style.css', 'sw.js',
        'engine_dry_run.js', 'engine_dry_run.py',
        'offline_create.js', 'offline_create.py',
        'real_match.js', 'real_match.py',
        'local_finish_stage.js', 'sync_stage.js', 'offline_nav.js', 'live_style.css',
        'live_perchanment.css', 'live_nav.css', 'live_tournament.css', 'offline_live_adapter.css',
        'offline_player_catalog.js', 'offline_player_catalog.css', 'offline_group_draft.js',
        'offline_group_draft.css', 'offline_groups_live.js',
        'offline_groups_live.css', 'offline_playoff_live.js',
        'offline_playoff_live.css', 'offline_results_live.js',
        'offline_results_live.css',
    }:
        abort(404)
    response = send_from_directory(_asset_dir(), filename)
    if filename == 'sw.js':
        response.headers['Service-Worker-Allowed'] = '/offline/'
        response.headers['Cache-Control'] = 'no-cache'
    return response
