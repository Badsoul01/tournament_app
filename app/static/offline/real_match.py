"""Apply a group or playoff match through the original WebManager on an isolated SQLite copy."""
import json
import sqlite3
import sys
import types
from flask import Flask
from werkzeug.datastructures import MultiDict

SOURCE = '/tmp/lab194b.sqlite'
WORK = '/tmp/lab202_work.sqlite'

# The browser copies bytes SOURCE -> WORK before executing this script.
with sqlite3.connect(WORK) as conn:
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Pracovni SQLite je poskozena')
    source = conn.execute('SELECT source_kind, source_tournament_id FROM offline_source').fetchall()
    if len(source) != 1 or source[0][0] not in ('live', 'local') or not isinstance(source[0][1], int):
        raise ValueError('Chybi jednoznacny puvod turnaje')
    tournament_id = source[0][1]

    # OFFLINE ADAPTER ONLY: JSON object key ordering must not decide the
    # destination of losers in the original Playoff.move_loser_to_placement_bracket.
    # The broad (parent) placement bracket comes before its child brackets.
    # Do this on the disposable WORK SQLite, before WebManager loads any tree.
    normalized_brackets = 0
    for bracket_id, raw_tree in conn.execute(
        'SELECT id, tree_data FROM brackets WHERE tournament_id=?', (tournament_id,)
    ).fetchall():
        if not raw_tree:
            continue
        tree = json.loads(raw_tree)
        branches = tree.get('placement_rounds')
        if not isinstance(branches, dict) or not branches:
            continue

        def placement_order(item):
            name, info = item
            ranks = info.get('ranks') if isinstance(info, dict) else None
            source_round = info.get('source_main_round') if isinstance(info, dict) else None
            if (not isinstance(ranks, (list, tuple)) or len(ranks) != 2
                    or not all(type(x) is int for x in ranks)
                    or type(source_round) is not int):
                raise ValueError(f'Neplatna placement vetev {name} v pavouku {bracket_id}')
            return (source_round, -(ranks[1] - ranks[0]), ranks[0])

        ordered = dict(sorted(branches.items(), key=placement_order))
        if list(ordered) != list(branches):
            tree['placement_rounds'] = ordered
            conn.execute('UPDATE brackets SET tree_data=? WHERE id=?',
                         (json.dumps(tree, ensure_ascii=False, separators=(',', ':')), bracket_id))
            normalized_brackets += 1

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

app = Flask('lab202_sandbox')
app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:////tmp/lab202_work.sqlite',
                  SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)

match_id = int(_lab202_match_id)
raw_sets = json.loads(_lab202_sets_json)
if not (1 <= len(raw_sets) <= 5):
    raise ValueError('Zadej 1 az 5 setu')
sets = []
for row in raw_sets:
    if not isinstance(row,list) or len(row)!=2 or any(type(v) is not int or v<0 or v>99 for v in row):
        raise ValueError('Neplatne hodnoty setu')
    if row[0] == row[1]:
        raise ValueError('Set nesmi skoncit remizou')
    sets.append(row)

with app.app_context():
    target = db.session.get(Match, match_id)
    if not target or target.tournament_id != tournament_id or (target.group_id is None and target.bracket_id is None) or target.is_finished:
        raise ValueError('Vybrany zapas neni dostupny nebo uz byl odehran')
    if target.player_a_id is None or target.player_b_id is None:
        raise ValueError('Zapasu chybi hrac')
    player_ids = (target.player_a_id, target.player_b_id)
    names = [db.session.get(Player, p).name for p in player_ids]
    form = MultiDict([('action','submit_result'), ('match_id',str(match_id))]
        + [('game_a[]', str(row[0])) for row in sets]
        + [('game_b[]', str(row[1])) for row in sets])
    try:
        is_playoff = target.bracket_id is not None
        is_consolation = False
        if is_playoff:
            bracket = db.session.get(Bracket, target.bracket_id)
            if bracket is None or bracket.tournament_id != tournament_id:
                raise ValueError('Neplatny pavouk zapasu')
            is_consolation = bool(bracket.is_consolation)
        manager = WebManager(tournament_id)
        if is_playoff and bracket.bracket_type == 'round_robin':
            # The original GroupManager handles consolation round-robin standings.
            from app.services.utils.match import evaluate
            from app.services.utils.transaction import atomic_result_update
            with atomic_result_update():
                finished = evaluate(match_id=match_id,
                    player_a_games=[str(row[0]) for row in sets],
                    player_b_games=[str(row[1]) for row in sets])
                if not finished:
                    raise ValueError('Neplatny vysledek minitabulky')
                manager.group_manager.handle_match_completion(match_id, manager.tournament)
        else:
            manager.process_match_action(form, is_playoff=is_playoff, is_consolation=is_consolation)
        db.session.expire_all()
        updated = db.session.get(Match, match_id)
        result_sets = [(x.score_a,x.score_b) for x in MatchResults.query.filter_by(match_id=match_id).order_by(MatchResults.set_number)]
        stats = [{'player_id':p.id, 'name':p.name,
                  'points': (GroupStats.query.filter_by(player_id=p.id).first().points if GroupStats.query.filter_by(player_id=p.id).first() else None)}
                 for p in Player.query.filter(Player.id.in_(player_ids)).all()]
        after = {
            'matches': Match.query.filter_by(tournament_id=tournament_id).count(),
            'finished': Match.query.filter_by(tournament_id=tournament_id,is_finished=True).count(),
            'sets': MatchResults.query.count(),
            'group_stats': GroupStats.query.count(),
            'brackets': {str(b.id): json.dumps(b.tree_data,sort_keys=True) for b in Bracket.query.filter_by(tournament_id=tournament_id)},
        }
        report = {'status':'OK','tournament_id':tournament_id,'match_id':match_id,'players':names,
                  'sets':result_sets,'winner_id':updated.winner_id,'finished':updated.is_finished,
                  'affected_player_stats':stats,
                  'before':{k:v for k,v in before.items() if k!='brackets'},
                  'after':{k:v for k,v in after.items() if k!='brackets'},
                  'playoff_tree_changed':any(json.loads(before['brackets'][k]) != json.loads(v)
                     for k,v in after['brackets'].items()),
                  'normalized_brackets':normalized_brackets,
                  'scope':'pouze docasna SQLite; IndexedDB uklada az JavaScript'}
    finally:
        db.session.remove()
        db.engine.dispose()

with sqlite3.connect(WORK) as conn:
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Zmenena SQLite neprosla integrity_check')
    if conn.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Zmenena SQLite ma neplatne cizi klice')
    row = conn.execute('SELECT is_finished, winner_id FROM matches WHERE id=?', (match_id,)).fetchone()
    stored = conn.execute('SELECT score_a, score_b FROM match_results WHERE match_id=? ORDER BY set_number', (match_id,)).fetchall()
    expected_winner = player_ids[0] if sum(a>b for a,b in sets)>sum(b>a for a,b in sets) else (player_ids[1] if sum(a>b for a,b in sets)<sum(b>a for a,b in sets) else None)
    if row != (1,expected_winner) or stored != [tuple(s) for s in sets]:
        raise ValueError('Oficialni vysledek se neulozil korektne')
    report['verified_on_disk'] = True
report_json=json.dumps(report,ensure_ascii=False)
report_json
