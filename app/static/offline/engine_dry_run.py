"""20.1B: test actual current WebManager against an isolated SQLite copy."""
import json
import sqlite3
import sys
import types
from flask import Flask
from werkzeug.datastructures import MultiDict

SOURCE = '/tmp/lab194b.sqlite'
WORK = '/tmp/lab201b_work.sqlite'

# The browser copies bytes SOURCE -> WORK before executing this script.
with sqlite3.connect(WORK) as conn:
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Pracovni SQLite je poskozena')
    source = conn.execute('SELECT source_kind, source_tournament_id FROM offline_source').fetchall()
    if source != [('live', 76)]:
        raise ValueError('Pro experiment 20.1B vyzadujeme live turnaj 76')
    before = {
        'matches': conn.execute('SELECT COUNT(*) FROM matches').fetchone()[0],
        'finished': conn.execute('SELECT COUNT(*) FROM matches WHERE is_finished=1').fetchone()[0],
        'sets': conn.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],
        'group_stats': conn.execute('SELECT COUNT(*) FROM group_stats').fetchone()[0],
        'brackets': {str(i): tree for i,tree in conn.execute('SELECT id, tree_data FROM brackets')},
    }

for name in ('app', 'app.models', 'app.services', 'app.services.utils', 'app.services.tournament', 'app.web'):
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = ['/home/pyodide/' + name.replace('.', '/')]
        sys.modules[name] = module

from app.models.models import db, Tournament, Match, MatchResults, GroupStats, Bracket, Player
from app.web.webmanager import WebManager

app = Flask('lab201b_sandbox')
app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:////tmp/lab201b_work.sqlite',
                  SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)

with app.app_context():
    target = db.session.get(Match, 1992)
    if not target or target.tournament_id != 76 or target.group_id is None or target.is_finished:
        raise ValueError('Zapas 1992 neni vhodny pro test')
    names = [db.session.get(Player, p).name for p in (target.player_a_id, target.player_b_id)]
    action = MultiDict([('action','submit_result'),('match_id','1992'),
                        ('game_a[]','11'),('game_a[]','11'),
                        ('game_b[]','5'),('game_b[]','8')])
    try:
        WebManager(76).process_match_action(action, is_playoff=False)
        db.session.expire_all()
        updated = db.session.get(Match, 1992)
        result_sets = [(x.score_a,x.score_b) for x in MatchResults.query.filter_by(match_id=1992).order_by(MatchResults.set_number)]
        stats = [{'player_id':p.id, 'name':p.name,
                  'points': (GroupStats.query.filter_by(player_id=p.id).first().points if GroupStats.query.filter_by(player_id=p.id).first() else None)}
                 for p in Player.query.filter(Player.id.in_([target.player_a_id,target.player_b_id])).all()]
        after = {
            'matches': Match.query.filter_by(tournament_id=76).count(),
            'finished': Match.query.filter_by(tournament_id=76,is_finished=True).count(),
            'sets': MatchResults.query.count(),
            'group_stats': GroupStats.query.count(),
            'brackets': {str(b.id):json.dumps(b.tree_data,sort_keys=True) for b in Bracket.query.filter_by(tournament_id=76)},
        }
        report = {'status':'OK','scope':'pouze docasna kopie v Pyodide',
                  'tournament_id':76,'match_id':1992,'players':names,'sets':result_sets,
                  'winner_id':updated.winner_id,'finished':updated.is_finished,
                  'affected_player_stats':stats,
                  'before':{k:v for k,v in before.items() if k!='brackets'},
                  'after':{k:v for k,v in after.items() if k!='brackets'},
                  'playoff_tree_changed':any(
                      json.loads(before['brackets'][key]) != json.loads(value)
                      for key,value in after['brackets'].items()),
                  'note':'Vysledek NENI ulozen do IndexedDB ani live DB'}
    finally:
        db.session.remove()
        db.engine.dispose()

report_json=json.dumps(report,ensure_ascii=False)
report_json
