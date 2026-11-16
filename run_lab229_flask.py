"""22.9A: isolated local Flask runner. NEVER deploy on VPS.

Checks database identity before serving any request. Uses only 127.0.0.1:5001.
"""
import os
from pathlib import Path
from sqlalchemy.engine import make_url

TARGET = 'offline_sync_lab226b'
URI = f'postgresql:///{TARGET}'

# Force DB before importing app or .env loading. Ignore stale flags from shell.
os.environ['DATABASE_URL'] = URI
os.environ['LAB222_ENABLE'] = '0'
os.environ['LAB228_ENABLE'] = '0'
os.environ['LAB229_ENABLE'] = '1'

from sqlalchemy import text
from app import create_app
from app.models.models import db
from app.services.tournament.offline_sync_lab229 import verify_isolation

app = create_app()
app.config['DEBUG'] = False
app.config['TESTING'] = False

with app.app_context():
    config_url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
    if config_url.database != TARGET or config_url.host is not None:
        raise RuntimeError('SAFETY STOP: Flask URI is not local lab clone')
    verify_isolation()
    with db.engine.connect() as conn:
        required = ('public.tournaments', 'public.matches', 'public.lab229_state', 'public.lab229_requests')
        missing = [name for name in required if conn.execute(text('SELECT to_regclass(:name)'), {'name': name}).scalar() is None]
        if missing:
            raise RuntimeError(f'SAFETY STOP: missing lab tables: {missing}')
        matches = conn.execute(text('SELECT COUNT(*) FROM public.matches WHERE tournament_id=76')).scalar()
        ledger = conn.execute(text('SELECT revision FROM public.lab229_state WHERE tournament_id=76')).scalar_one_or_none()
    if ledger is None:
        raise RuntimeError('SAFETY STOP: no lab229 revision row for tournament 76')
    print(f'LAB229 ISOLATED: DB={TARGET} | tournament 76 matches={matches} | revision={ledger}')
    print('Open http://127.0.0.1:5001/tournament/76/groups (READ ONLY for now)')
    print('Do NOT submit result yet: verify online adapter is installed in tournament_routes.py.')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)
