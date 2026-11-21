"""Import a finished locally-created PWA tournament into staging or production.

Deliberately separate from existing /api/offline/stage/<tid>/sync.
Uses a complete snapshot + operation preview, not an untrusted client-side SQL dump.
The importer copies approved data fields through ORM; never executes uploaded SQL.
"""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.models.models import (
    db, Organizer, Tournament, Group, Player, Bracket, Match, MatchResults,
    GroupStats, PlayoffStats, ConsolationStats,
)
from app.services.tournament.tournament import Tournament as TournamentOrchestrator

local_import_bp = Blueprint('offline_local_import_stage', __name__, url_prefix='/api/offline/stage/local')
prod_local_import_bp = Blueprint('offline_local_import_prod', __name__, url_prefix='/api/offline')
MAX_SQLITE = 2 * 1024 * 1024
MAX_OPERATIONS = 300

class LocalImportError(Exception):
    def __init__(self, message, status=400, code='INVALID_IMPORT'):
        super().__init__(message)
        self.status, self.code = status, code

@local_import_bp.errorhandler(LocalImportError)
def _error(e):
    db.session.rollback()
    return jsonify(status='ERROR', code=e.code, message=str(e)), e.status


prod_local_import_bp.register_error_handler(LocalImportError, _error)

def _staging_only():
    url = make_url(current_app.config['SQLALCHEMY_DATABASE_URI'])
    if (os.environ.get('OFFLINE_SYNC_STAGING') != '1' or
        not url.drivername.startswith('postgresql') or
        not url.database or not url.database.startswith('offline_') or
        url.database in {'offline_live', 'offline_production'}):
        raise LocalImportError('Nepovolená databáze.', 503, 'DISABLED')
    if current_app.secret_key in ('', None, 'zalozni_tajny_kod'):
        raise LocalImportError('Staging vyžaduje vlastní SECRET_KEY.', 503, 'WEAK_SECRET')
    if db.session.execute(text('select current_database()')).scalar_one() != url.database:
        raise LocalImportError('Chybná databáze.', 503, 'WRONG_DATABASE')



def _production_only():
    """Require explicit production enablement, matching database, and a secret header."""
    url = make_url(current_app.config['SQLALCHEMY_DATABASE_URI'])
    if (os.environ.get('OFFLINE_SYNC_ENABLED') != '1' or
            not url.drivername.startswith('postgresql') or
            not url.database or url.database.startswith('offline_')):
        raise LocalImportError('Produkční import není povolen.', 503, 'DISABLED')
    if db.session.execute(text('SELECT current_database()')).scalar_one() != url.database:
        raise LocalImportError('Nesouhlasí databáze.', 503, 'WRONG_DATABASE')
    secret = os.environ.get('OFFLINE_SYNC_TOKEN', '')
    provided = request.headers.get('X-Offline-Token', '')
    if len(secret) < 24:
        raise LocalImportError('Není nakonfigurován synchronizační klíč.', 503, 'MISSING_SECRET')
    if not hmac.compare_digest(provided, secret):
        raise LocalImportError('Neplatný synchronizační klíč.', 403, 'FORBIDDEN')
    uid_raw = os.environ.get('OFFLINE_SYNC_ORGANIZER_ID', '')
    try:
        uid = int(uid_raw)
    except ValueError:
        raise LocalImportError('Není nastaven organizátor importu.', 503, 'MISSING_ORGANIZER')
    if uid <= 0 or db.session.get(Organizer, uid) is None:
        raise LocalImportError('Organizátor importu neexistuje.', 503, 'MISSING_ORGANIZER')
    return uid

def _rows(conn, table):
    return [dict(r) for r in conn.execute('select * from ' + table)]


def _load_sqlite(data):
    if len(data) > MAX_SQLITE or not data.startswith(b'SQLite format 3\x00'):
        raise LocalImportError('Neplatný nebo příliš velký soubor SQLite.')
    # SQLite opens upload READ-ONLY, and no extension loading is supported.
    with tempfile.NamedTemporaryFile(suffix='.sqlite') as f:
        f.write(data); f.flush()
        conn = sqlite3.connect('file:' + f.name + '?mode=ro&immutable=1', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise LocalImportError('Poškozená SQLite.')
            tables = ('offline_source','offline_local_identity','tournaments','groups','players',
                      'brackets','matches','match_results','group_stats','playoff_stats','consolation_stats')
            found = {r[0] for r in conn.execute('select name from sqlite_master where type="table"')}
            if not set(tables) <= found:
                raise LocalImportError('SQLite nemá požadované tabulky.')
            return {name: _rows(conn, name) for name in tables}
        finally:
            conn.close()


def _keymap(rows, label):
    result = {}
    for row in rows:
        key = row['id']
        if type(key) is not int or key <= 0 or key in result:
            raise LocalImportError('Neplatný primární klíč: ' + label)
        result[key] = row
    return result


def _require(cond, msg):
    if not cond:
        raise LocalImportError(msg)


def _check_snapshot(tables, preview):
    t = tables['tournaments']
    src = tables['offline_source']
    ids = tables['offline_local_identity']
    _require(len(t) == len(src) == len(ids) == 1, 'Očekáván jediný lokální turnaj.')
    local_t = t[0]
    _require(src[0]['source_kind'] == 'local' and src[0]['tournament_id'] == local_t['id'], 'Nejde o lokální turnaj.')
    _require(ids[0]['server_tournament_id'] is None, 'Turnaj už má serverové ID.')
    try:
        local_uuid = str(UUID(ids[0]['local_uuid']))
    except (ValueError, TypeError, AttributeError):
        raise LocalImportError('Chybí platné UUID turnaje.')
    _require(len(tables['players']) > 0 and len(tables['matches']) > 0, 'Prázdný turnaj.')
    _require(len(tables['players']) <= 128 and len(tables['matches']) <= MAX_OPERATIONS, 'Příliš rozsáhlý turnaj.')
    _require(len(tables['groups']) <= 16 and len(tables['brackets']) <= 4, 'Neobvyklý počet skupin či pavouků.')
    groups = _keymap(tables['groups'], 'groups')
    players = _keymap(tables['players'], 'players')
    matches = _keymap(tables['matches'], 'matches')
    brackets = _keymap(tables['brackets'], 'brackets')
    _require(all(r['tournament_id'] == local_t['id'] for name in ('groups','players','matches','brackets') for r in tables[name]), 'Cizí turnaj v SQLite.')
    _require(all(p['group_id'] in groups for p in players.values()), 'Hráč bez skupiny.')
    _require(all((m['group_id'] in groups) != (m['bracket_id'] in brackets) for m in matches.values()), 'Zápas nemá právě jednu skupinu nebo pavouka.')
    # A BYE is an automatically finished playoff slot, not a played match.
    # Never classify unfinished/unresolved slots as BYE merely because an ID is NULL.
    real_matches = {}
    for mid, m in matches.items():
        a, b, winner = m['player_a_id'], m['player_b_id'], m['winner_id']
        _require(m['is_finished'] == 1, 'Turnaj obsahuje nedokončený zápas.')
        _require(a is None or a in players, 'Neplatný hráč A.')
        _require(b is None or b in players, 'Neplatný hráč B.')
        if a is not None and b is not None:
            _require(a != b and winner in (a, b), 'Neplatný vítěz skutečného zápasu.')
            real_matches[mid] = m
        else:
            _require(m['bracket_id'] in brackets and m['group_id'] is None,
                     'Volný los je povolen pouze v playoff.')
            expected_winner = a if b is None else b
            _require(winner == expected_winner, 'Nesprávně vyhodnocený volný los.')
    sets_by_match = {}
    for r in tables['match_results']:
        _require(r['match_id'] in matches and r['set_number'] >= 1 and r['score_a'] != r['score_b'], 'Neplatný set.')
        sets_by_match.setdefault(r['match_id'], []).append(r)
    for mid, sets in sets_by_match.items():
        sets.sort(key=lambda r: r['set_number'])
        _require([x['set_number'] for x in sets] == list(range(1, len(sets)+1)), 'Chybné pořadí setů.')
        wins_a = sum(s['score_a'] > s['score_b'] for s in sets)
        wins_b = sum(s['score_b'] > s['score_a'] for s in sets)
        expected = matches[mid]['player_a_id'] if wins_a > wins_b else matches[mid]['player_b_id']
        _require(wins_a != wins_b and matches[mid]['winner_id'] == expected, 'Nesouhlasí vítěz zápasu.')
    _require(set(sets_by_match) == set(real_matches), 'Sety musí být právě u skutečných zápasů.')
    _require(isinstance(preview, dict) and preview.get('format') == 'spravaturnaje-pending-operations-preview-v1' and preview.get('tournament_id') == local_t['id'], 'Neplatný export fronty.')
    ops = preview.get('operations')
    _require(isinstance(ops, list) and preview.get('count') == len(ops) == len(real_matches), 'Počet operací se neshoduje.')
    seen_ids, seen_matches = set(), set()
    for op in ops:
        try: rid = str(UUID(op['request_id']))
        except (TypeError, KeyError, ValueError, AttributeError): raise LocalImportError('Neplatné request_id.')
        mid = op.get('match_id')
        _require(rid not in seen_ids and mid in real_matches and mid not in seen_matches and op.get('action') == 'submit_result' and op.get('tournament_id') == local_t['id'], 'Neplatná nebo duplicitní operace.')
        seen_ids.add(rid); seen_matches.add(mid)
        expected = [[s['score_a'], s['score_b']] for s in sets_by_match[mid]]
        _require(op.get('sets') == expected, 'Výsledek ve frontě se neshoduje se SQLite.')
    _require(seen_matches == set(real_matches), 'Pro některý skutečný zápas chybí operace.')
    # Validate the bracket JSON tree: every referenced match ID must belong to its bracket.
    for b in brackets.values():
        tree = json.loads(b['tree_data']) if isinstance(b['tree_data'], str) else b['tree_data']
        _require(isinstance(tree, dict), 'Neplatný strom playoff.')
        for value in (tree.get('rounds') or {}).values():
            _check_slots(value, b['id'], matches)
        for branch in (tree.get('placement_rounds') or {}).values():
            _check_slots(branch.get('matches', []), b['id'], matches)
    for name in ('group_stats','playoff_stats','consolation_stats'):
        _require(all(r['player_id'] in players for r in tables[name]), 'Statistiky odkazují na cizího hráče.')
    _require(local_t['name'] and len(local_t['name']) <= 100, 'Neplatný název turnaje.')
    return local_uuid, local_t


def _check_slots(value, bracket_id, matches):
    if isinstance(value, list):
        for item in value: _check_slots(item, bracket_id, matches)
    elif type(value) is int:
        _require(value in matches and matches[value]['bracket_id'] == bracket_id, 'Strom playoff odkazuje na cizí zápas.')
    elif isinstance(value, str):
        _require(value in ('Čeká se..', 'BYE', 'None') or len(value) <= 20, 'Neplatný slot.')
    elif value is not None:
        raise LocalImportError('Neplatný slot playoff.')


def _remap_slots(value, match_map):
    if isinstance(value, list): return [_remap_slots(v, match_map) for v in value]
    if type(value) is int: return match_map[value]
    return value


def _remap_tree(value, match_map):
    tree = json.loads(value) if isinstance(value, str) else value
    for stage in ('rounds',):
        if stage in tree:
            tree[stage] = {k:_remap_slots(v, match_map) for k,v in tree[stage].items()}
    if 'placement_rounds' in tree:
        for branch in tree['placement_rounds'].values():
            branch['matches'] = _remap_slots(branch.get('matches',[]), match_map)
    if 'matches' in tree:
        tree['matches'] = _remap_slots(tree['matches'], match_map)
    return tree


def _copy(tables, t, uid, uuid, digest):
    # The UUID identity has a UNIQUE constraint (installed by the separate SQL migration).
    new_t = Tournament(
        name=t['name'], date=datetime.fromisoformat(t['date']), location=t['location'],
        tournament_format=t['tournament_format'], include_in_global_stats=bool(t['include_in_global_stats']),
        group_match_format=t['group_match_format'], playoff_match_format=t['playoff_match_format'],
        advance_per_group=t['advance_per_group'], group_elimination_action=t['group_elimination_action'],
        playoff_elimination_action=t['playoff_elimination_action'], total_players=t['total_players'],
        total_players_in_playoff=t['total_players_in_playoff'], has_playoff=bool(t['has_playoff']),
        has_consolation=bool(t['has_consolation']), consolation_format=t['consolation_format'],
        is_finished=False, organizer_id=uid)
    db.session.add(new_t); db.session.flush()
    group_map, player_map, bracket_map, match_map = {}, {}, {}, {}
    for row in tables['groups']:
        obj = Group(name=row['name'], is_consolation=bool(row['is_consolation']), is_finished=bool(row['is_finished']), tournament_id=new_t.id)
        db.session.add(obj); db.session.flush(); group_map[row['id']] = obj.id
    for row in tables['players']:
        obj = Player(name=row['name'], group_seed=row['group_seed'], tournament_id=new_t.id,
                     group_id=group_map[row['group_id']], global_player_id=None)
        db.session.add(obj); db.session.flush(); player_map[row['id']] = obj.id
    for row in tables['brackets']:
        obj = Bracket(name=row['name'], tournament_id=new_t.id, bracket_type=row['bracket_type'],
                      is_consolation=bool(row['is_consolation']), tree_data={})
        db.session.add(obj); db.session.flush(); bracket_map[row['id']] = obj.id
    for row in tables['matches']:
        obj = Match(match_type=row['match_type'], match_format=row['match_format'],
                    is_finished=bool(row['is_finished']), is_in_progress=bool(row['is_in_progress']),
                    seed_a=row['seed_a'], seed_b=row['seed_b'], tournament_id=new_t.id,
                    group_id=group_map.get(row['group_id']), bracket_id=bracket_map.get(row['bracket_id']),
                    player_a_id=player_map.get(row['player_a_id']), player_b_id=player_map.get(row['player_b_id']),
                    winner_id=player_map.get(row['winner_id']))
        db.session.add(obj); db.session.flush(); match_map[row['id']] = obj.id
    for row in tables['brackets']:
        obj = db.session.get(Bracket, bracket_map[row['id']]); obj.tree_data = _remap_tree(row['tree_data'], match_map)
    for row in tables['match_results']:
        db.session.add(MatchResults(match_id=match_map[row['match_id']],set_number=row['set_number'],
                                    score_a=row['score_a'],score_b=row['score_b']))
    fields = {
        'group_stats': (GroupStats, ['points','games_win','games_lost','balls_win','balls_lost']),
        'playoff_stats': (PlayoffStats, ['games_win','games_lost','balls_win','balls_lost','final_rank','points_gained']),
        'consolation_stats': (ConsolationStats, ['points','games_win','games_lost','balls_win','balls_lost','final_rank']),
    }
    for name,(cls, cols) in fields.items():
        for row in tables[name]:
            db.session.add(cls(player_id=player_map[row['player_id']], **{k:row[k] for k in cols}))
    db.session.execute(text('INSERT INTO offline_local_imports (local_uuid, tournament_id, organizer_id, payload_sha256) VALUES (:uuid,:tid,:uid,:digest)'),
                       dict(uuid=uuid,tid=new_t.id,uid=uid,digest=digest))
    db.session.flush()
    return new_t.id


@local_import_bp.post('/finish')
@prod_local_import_bp.post('/local/finish')
def import_finished():
    # The staging URL remains isolated and unchanged. The production URL needs
    # a server-configured token and attaches the import to an existing organizer.
    if request.blueprint == 'offline_local_import_prod':
        uid = _production_only()
    else:
        _staging_only()
        uid = None
    origin = request.headers.get('Origin')
    if (request.headers.get('X-Offline-Sync') != '1' or
        (origin and urlsplit(origin).netloc != request.host)):
        raise LocalImportError('Neplatný původ požadavku.', 403, 'ORIGIN')
    if request.content_length is None or request.content_length > MAX_SQLITE + 256*1024:
        raise LocalImportError('Neplatná velikost požadavku.', 413, 'TOO_LARGE')
    sqlite_file = request.files.get('sqlite')
    queue_file = request.files.get('operations')
    if not sqlite_file or not queue_file:
        raise LocalImportError('Požadovány soubory sqlite a operations.')
    data = sqlite_file.read(MAX_SQLITE+1)
    raw_ops = queue_file.read(256*1024+1)
    if len(raw_ops) > 256*1024: raise LocalImportError('Příliš velká fronta.', 413)
    try: ops = json.loads(raw_ops)
    except (ValueError, UnicodeDecodeError): raise LocalImportError('Neplatný JSON fronty.')
    tables = _load_sqlite(data)
    uuid, tournament = _check_snapshot(tables, ops)
    digest = hashlib.sha256(json.dumps({'snapshot':tables, 'operations':ops}, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    prior = db.session.execute(text('SELECT tournament_id, organizer_id, payload_sha256 FROM offline_local_imports WHERE local_uuid=:uuid'), {'uuid':uuid}).mappings().first()
    if prior:
        if prior['organizer_id'] != uid or prior['payload_sha256'] != digest:
            raise LocalImportError('UUID již existuje s jiným obsahem či vlastníkem.',409,'UUID_CONFLICT')
        existing = db.session.get(Tournament, prior['tournament_id'])
        if existing and existing.is_finished:
            return jsonify(status='ALREADY_IMPORTED', tournament_id=existing.id, local_uuid=uuid)
        # If the previous request stopped during finishing, finalize existing record.
        if not existing: raise LocalImportError('Nekonzistentní identita importu.',409,'UUID_CONFLICT')
        tid = existing.id
    else:
        try:
            tid = _copy(tables, tournament, uid, uuid, digest)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise LocalImportError('Současně běží jiný import stejného UUID. Zopakuj požadavek.',409,'RETRY')
        except Exception:
            db.session.rollback()
            raise
    # This project's finish_existing_tournament() commits internally.
    # Therefore creation and finishing are TWO resumable transactions.
    if not TournamentOrchestrator.finish_existing_tournament(tid):
        raise LocalImportError('Import proběhl, ale server odmítl ukončení turnaje.',409,'FINISH_PENDING')
    return jsonify(status='COMMITTED', tournament_id=tid, local_uuid=uuid,
                   finished=True, imported_matches=len(tables['matches']))
