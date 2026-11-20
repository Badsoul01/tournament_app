"""Offline PWA: edit one finished match on a DISPOSABLE SQLite work copy.

The caller writes the current SQLite to WORK, sets _lab202_match_id and
_lab202_sets_json, executes this script, and only persists WORK if report_json
confirms verified_on_disk. No changes to production databases.
"""
import json
import sqlite3
import sys
import types
from flask import Flask
from werkzeug.datastructures import MultiDict

WORK = '/tmp/lab202_work.sqlite'


def snapshot_finished(conn, tournament_id):
    """Protect ALL previously finished matches, including downstream branches."""
    rows = conn.execute('''
        SELECT id, group_id, bracket_id, player_a_id, player_b_id,
                    winner_id, is_finished, match_type
        FROM matches
        WHERE tournament_id=? AND is_finished=1
    ''', (tournament_id,)).fetchall()
    result = {}
    for row in rows:
        mid = row[0]
        sets = conn.execute('''
            SELECT set_number, score_a, score_b FROM match_results
            WHERE match_id=? ORDER BY set_number
        ''', (mid,)).fetchall()
        result[mid] = (tuple(row[1:]), tuple(tuple(s) for s in sets))
    return result


with sqlite3.connect(WORK) as conn:
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Pracovní SQLite je poškozená.')
    origin = conn.execute('SELECT source_kind, source_tournament_id FROM offline_source').fetchall()
    if len(origin) != 1 or origin[0][0] != 'local' or type(origin[0][1]) is not int:
        raise ValueError('Opravy jsou nyní podporované jen u lokálně vytvořeného turnaje.')
    tournament_id = origin[0][1]
    previous = snapshot_finished(conn, tournament_id)

for name in ('app', 'app.models', 'app.services', 'app.services.utils',
             'app.services.tournament', 'app.web'):
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = ['/home/pyodide/' + name.replace('.', '/')]
        sys.modules[name] = module

from app.models.models import db, Match, MatchResults, Bracket
from app.web.webmanager import WebManager

app = Flask('offline_match_edit')
app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:////tmp/lab202_work.sqlite',
                  SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)

match_id = int(_lab202_match_id)
sets = json.loads(_lab202_sets_json)
if not isinstance(sets, list) or not (1 <= len(sets) <= 5):
    raise ValueError('Oprava vyžaduje 1 až 5 setů.')
for row in sets:
    if (not isinstance(row, list) or len(row) != 2 or
        any(type(v) is not int or not 0 <= v <= 99 for v in row) or row[0] == row[1]):
        raise ValueError('Neplatné skóre některého setu.')
if match_id not in previous:
    raise ValueError('Opravovat lze pouze již odehraný zápas.')

with app.app_context():
    try:
        target = db.session.get(Match, match_id)
        if (target is None or target.tournament_id != tournament_id or
            not target.is_finished or target.player_a_id is None or
            target.player_b_id is None):
            raise ValueError('Zápas nelze opravit.')
        is_playoff = target.bracket_id is not None
        is_consolation = False
        bracket = None
        if is_playoff:
            bracket = db.session.get(Bracket, target.bracket_id)
            if bracket is None or bracket.tournament_id != tournament_id:
                raise ValueError('Zápas má neplatný pavouk.')
            is_consolation = bool(bracket.is_consolation)
        elif target.group_id is None:
            raise ValueError('Zápas není přiřazen ke skupině ani pavouku.')

        manager = WebManager(tournament_id)
        if is_playoff and bracket.bracket_type == 'round_robin':
            # Existing live code handles consolation minigroups with GroupManager.
            from app.services.utils.match import evaluate
            from app.services.utils.transaction import atomic_result_update
            with atomic_result_update():
                ok = evaluate(match_id=match_id,
                              player_a_games=[str(row[0]) for row in sets],
                              player_b_games=[str(row[1]) for row in sets])
                if not ok:
                    raise ValueError('Neplatný výsledek minitabulky.')
                manager.group_manager.handle_match_completion(match_id, manager.tournament)
        else:
            form = MultiDict([('action', 'submit_result'), ('match_id', str(match_id))]
                             + [('game_a[]', str(row[0])) for row in sets]
                             + [('game_b[]', str(row[1])) for row in sets])
            manager.process_match_action(form, is_playoff=is_playoff,
                                         is_consolation=is_consolation)
    finally:
        db.session.remove()
        db.engine.dispose()

with sqlite3.connect(WORK) as conn:
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Opravená SQLite neprošla integrity_check.')
    if conn.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Opravená SQLite má porušené cizí klíče.')
    after = snapshot_finished(conn, tournament_id)
    if match_id not in after:
        raise ValueError('Opravovaný zápas není dokončený.')
    for old_id, old_state in previous.items():
        if old_id == match_id:
            continue
        if after.get(old_id) != old_state:
            raise ValueError('Oprava by změnila již odehraný navazující zápas.')
    actual = conn.execute('''
        SELECT score_a, score_b FROM match_results
        WHERE match_id=? ORDER BY set_number
    ''', (match_id,)).fetchall()
    if [list(row) for row in actual] != sets:
        raise ValueError('Opravené sety nebyly správně uloženy.')
    data = conn.execute('''
        SELECT winner_id, player_a_id, player_b_id FROM matches WHERE id=?
    ''', (match_id,)).fetchone()
    wins_a = sum(a > b for a, b in sets)
    wins_b = sum(b > a for a, b in sets)
    winner = data[1] if wins_a > wins_b else data[2] if wins_b > wins_a else None
    if data[0] != winner or (data[0] is None and is_playoff):
        raise ValueError('Nesouhlasí vítěz opraveného zápasu.')

report_json = json.dumps({'status': 'OK', 'match_id': match_id,
                          'tournament_id': tournament_id, 'sets': sets,
                          'verified_on_disk': True,
                          'protected_finished_matches': len(previous)-1},
                         ensure_ascii=False)
report_json
