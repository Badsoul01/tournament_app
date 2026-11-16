"""Create a new local-only tournament using the original Tournament builder and engine.
Run inside browser Pyodide with globals `_offline_config_json` and `_offline_uuid`.
Never talks to server. /tmp/new_offline.sqlite is created fresh.
"""
import json, sqlite3, sys, types
from datetime import datetime, timezone
from flask import Flask

settings = json.loads(_offline_config_json)
if not isinstance(settings, dict): raise ValueError('Neplatne nastaveni')
groups = settings.get('groups')
if not isinstance(groups, dict) or len(groups) < 2 or len(groups) > 8: raise ValueError('Pozaduji 2 az 8 skupin')
if list(groups) != [chr(65+i) for i in range(len(groups))]: raise ValueError('Skupiny musi jit postupne A, B, C...')
players = [str(p).strip() for group in groups.values() for p in group]
if any(not isinstance(g,list) or len(g)<2 or len(g)>8 for g in groups.values()): raise ValueError('Ve skupine musi byt 2 az 8 hracu')
if not players or len(set(p.casefold() for p in players)) != len(players) or any(not p for p in players): raise ValueError('Prazdna nebo duplicitni jmena')
adv = settings.get('advance_per_group')
if type(adv) is not int or adv not in (1,2,3,4): raise ValueError('Neplatny pocet postupujicich')
if any(len(g) <= adv for g in groups.values()): raise ValueError('Ve skupine musi byt vice hracu nez postupujicich (prvni prototyp)')
if settings.get('group_elimination_action') not in ('KO','playoff_b'): raise ValueError('Neplatna utesha')
if settings.get('playoff_elimination_action') not in ('KO','consolation'): raise ValueError('Neplatne playoff')
if settings.get('group_match_format') not in (2,3,4,5) or settings.get('playoff_match_format') not in (2,3,4,5): raise ValueError('Neplatny format zapasu')
if not isinstance(settings.get('name'),str) or not settings['name'].strip(): raise ValueError('Chybi nazev')
datetime.strptime(settings['date'], '%Y-%m-%d')
if not isinstance(_offline_uuid, str) or len(_offline_uuid) != 36: raise ValueError('Chybi UUID')

for name in ('app','app.models','app.services','app.services.utils','app.services.tournament'):
    if name not in sys.modules:
        m=types.ModuleType(name)
        m.__path__=['/home/pyodide/'+name.replace('.','/')]
        sys.modules[name]=m

# The original tournament module imports SetupWizard for type hints only. The
# full server wizard imports requests, BeautifulSoup, config and live ranking;
# none of those belong in the isolated offline generator.
module_name='app.services.tournament.setupwizard'
if module_name not in sys.modules:
    m=types.ModuleType(module_name)
    m.SetupWizard=type('SetupWizard', (), {})
    sys.modules[module_name]=m

from app.models.models import db
from app.services.tournament.tournament import Tournament

class OfflineWizard:
    def __init__(self, data):
        self.name=data['name'].strip()
        self.date=data['date']
        self.location=data.get('location','')
        self.tournament_format='groups'
        self.include_in_global_stats=bool(data.get('include_in_global_stats',False))
        self.group_match_format=data['group_match_format']
        self.playoff_match_format=data['playoff_match_format']
        self.advance_per_group=data['advance_per_group']
        self.group_elimination_action=data['group_elimination_action']
        self.playoff_elimination_action=data['playoff_elimination_action']
        self.groups=data['groups']
        self.is_single_group=False
        self.total_tournament_players=sum(map(len,self.groups.values()))
        self.total_players_advance_to_playoff=sum(min(len(g),self.advance_per_group) for g in self.groups.values())

path='/tmp/new_offline.sqlite'
import os
if os.path.exists(path): os.remove(path)
app=Flask('offline_create_browser')
app.config.update(SECRET_KEY='isolated-local-only', SQLALCHEMY_DATABASE_URI='sqlite:////tmp/new_offline.sqlite', SQLALCHEMY_TRACK_MODIFICATIONS=False)
# db is one shared instance, never attach a second app to an already-bound runtime.
db.init_app(app)
try:
    with app.app_context():
        db.create_all()
        with app.test_request_context('/local-create'):
            made=Tournament(OfflineWizard(settings))
            if made.id != 1: raise ValueError('Neocekavane lokalni ID')
        db.session.remove()
        db.engine.dispose()
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE offline_local_identity (local_uuid TEXT PRIMARY KEY NOT NULL, server_tournament_id INTEGER NULL, created_at_utc TEXT NOT NULL)')
        conn.execute('CREATE TABLE offline_source (tournament_id INTEGER PRIMARY KEY, source_kind TEXT NOT NULL, source_tournament_id INTEGER NOT NULL, original_organizer_id INTEGER, export_created_at_utc TEXT NOT NULL, import_version INTEGER NOT NULL)')
        now=datetime.now(timezone.utc).isoformat()
        conn.execute('INSERT INTO offline_local_identity VALUES (?,NULL,?)',(_offline_uuid,now))
        conn.execute("INSERT INTO offline_source VALUES (1,'local',1,NULL,?,1)",(now,))
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('SQLite poskozena')
        if conn.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Neplatne reference SQLite')
        report={k:conn.execute('SELECT COUNT(*) FROM '+k).fetchone()[0] for k in ('tournaments','groups','players','matches','brackets')}
        conn.commit()
    result_json=json.dumps({'status':'LOCAL_CREATED','local_uuid':_offline_uuid,**report},ensure_ascii=False)
finally:
    pass
result_json
