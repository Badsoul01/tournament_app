"""Isolated staging-only offline batch synchronization. Never register on production.

Register via app.register_blueprint(stage_sync_bp) only when the app is
explicitly configured with OFFLINE_SYNC_STAGING=1 and an offline_* PG database.
"""
import hashlib
import json
import os
from uuid import UUID
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import text
from sqlalchemy.engine import make_url
from werkzeug.datastructures import MultiDict

from app.models.models import (
    db, Bracket, Match, MatchResults, Organizer, Tournament,
    TournamentSyncRequest, TournamentSyncState,
)
from app.services.utils.match import evaluate
from app.services.utils.transaction import atomic_result_update, atomic_sync_update
from app.web.webmanager import WebManager

stage_sync_bp = Blueprint('offline_stage_sync', __name__, url_prefix='/api/offline/stage')


class SyncStop(Exception):
    def __init__(self, message, status=409, code='SYNC_REJECTED'):
        super().__init__(message)
        self.status = status
        self.code = code


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _check_environment():
    url = make_url(current_app.config['SQLALCHEMY_DATABASE_URI'])
    if (os.environ.get('OFFLINE_SYNC_STAGING') != '1' or
            not url.drivername.startswith('postgresql') or
            not url.database or not url.database.startswith('offline_') or
            url.database in {'offline_production', 'offline_live'}):
        raise SyncStop('Staging synchronizace není povolena.', 503, 'DISABLED')
    if current_app.secret_key in (None, '', 'zalozni_tajny_kod'):
        raise SyncStop('Staging vyžaduje vlastní SECRET_KEY.', 503, 'WEAK_SECRET')
    actual = db.session.execute(text('SELECT current_database()')).scalar_one()
    if actual != url.database:
        raise SyncStop('Nesouhlasí cílová databáze.', 503, 'WRONG_DATABASE')


def _authorize(tid):
    # No anonymous sync and no ownership assignment via this endpoint.
    uid = session.get('organizer_id')
    tournament = db.session.get(Tournament, tid)
    if (type(uid) is not int or tournament is None or
            tournament.organizer_id != uid or db.session.get(Organizer, uid) is None):
        raise SyncStop('Přihlas se na testovacím webu jako vlastník turnaje.', 403, 'FORBIDDEN')
    if tournament.is_finished:
        raise SyncStop('Turnaj je již uzamčený.', 409, 'LOCKED')
    return tournament


def _parse_batch(body, tid):
    if not isinstance(body, dict) or body.get('format') != 'spravaturnaje-offline-batch-v1':
        raise SyncStop('Neznámý formát dávky.', 400, 'INVALID_BATCH')
    if body.get('tournament_id') != tid or type(body.get('base_revision')) is not int:
        raise SyncStop('Chybné ID turnaje nebo výchozí revize.', 400, 'INVALID_BATCH')
    ops = body.get('operations')
    catalog = body.get('match_catalog')
    if not isinstance(ops, list) or not 1 <= len(ops) <= 300 or not isinstance(catalog, list) or len(catalog) > 300:
        raise SyncStop('Neplatný počet operací nebo katalog zápasů.', 400, 'INVALID_BATCH')
    metadata = {}
    for row in catalog:
        if not isinstance(row, dict):
            raise SyncStop('Neplatný katalog.', 400, 'INVALID_BATCH')
        mid = row.get('match_id')
        if type(mid) is not int or mid <= 0 or mid in metadata:
            raise SyncStop('Nejednoznačný zápas v katalogu.', 400, 'INVALID_BATCH')
        a, b = row.get('player_a_id'), row.get('player_b_id')
        if type(a) is not int or type(b) is not int or a == b:
            raise SyncStop('Chybní hráči v katalogu.', 400, 'INVALID_BATCH')
        kind = row.get('kind')
        if kind not in {'group', 'playoff'}:
            raise SyncStop('Neznámý typ zápasu.', 400, 'INVALID_BATCH')
        if kind == 'group':
            if type(row.get('group_id')) is not int:
                raise SyncStop('Chybí skupina.', 400, 'INVALID_BATCH')
        else:
            if type(row.get('is_consolation')) is not bool or row.get('bracket_type') not in {'elimination', 'round_robin'}:
                raise SyncStop('Chybný pavouk.', 400, 'INVALID_BATCH')
        metadata[mid] = row
    ids, matches, clean = set(), set(), []
    for index, op in enumerate(ops, 1):
        if not isinstance(op, dict) or op.get('action') != 'submit_result' or op.get('tournament_id') != tid:
            raise SyncStop(f'Operace {index}: neplatná akce.', 400, 'INVALID_BATCH')
        rid, mid, sets = op.get('request_id'), op.get('match_id'), op.get('sets')
        try:
            if not isinstance(rid, str) or len(rid) > 64:
                raise ValueError()
            UUID(rid)
        except (ValueError, AttributeError):
            raise SyncStop(f'Operace {index}: neplatné request_id.', 400, 'INVALID_BATCH')
        if rid in ids or type(mid) is not int or mid in matches or mid not in metadata:
            raise SyncStop(f'Operace {index}: duplicita nebo chybí popis zápasu.', 400, 'INVALID_BATCH')
        if not isinstance(sets, list) or not 1 <= len(sets) <= 7:
            raise SyncStop(f'Operace {index}: chybné sety.', 400, 'INVALID_BATCH')
        for pair in sets:
            if (not isinstance(pair, list) or len(pair) != 2 or
                    any(type(n) is not int or not 0 <= n <= 99 for n in pair) or pair[0] == pair[1]):
                raise SyncStop(f'Operace {index}: chybné skóre.', 400, 'INVALID_BATCH')
        ids.add(rid)
        matches.add(mid)
        clean.append({'request_id': rid, 'tournament_id': tid, 'action': 'submit_result',
                      'match_id': mid, 'sets': sets})
    return clean, metadata


# Compatibility ONLY for the historic terminal replay of tournament 76.
# The terminal bridge hashed {tournament_id, request_id, match_id, sets},
# whereas the HTTP service hashes {op, match}. The recovered third request
# was saved with a different request_id before the Android JSON was corrected.
_LEGACY_76_RECOVERED = 'recovered-1994-e71dd41c315cb5290d4c5773'
_LEGACY_76_ORIGINAL = 'dedf7d11-5360-47ff-9b9e-47e1f739e4a1'


def _legacy_digest(op, *, request_id=None):
    payload = {
        'tournament_id': op['tournament_id'],
        'request_id': request_id if request_id is not None else op['request_id'],
        'match_id': op['match_id'],
        'sets': op['sets'],
    }
    return hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()


def _recognize_legacy_76(tid, revision, ops, records, state):
    """Read-only check. Never migrate/overwrite the terminal ledger.

    Only confirms the one historically known 22-operation replay, matching
    every sequence position and digest. The recovered request is validated
    using its saved ID and the actual group-match score.
    """
    if not (tid == 76 and revision == 0 and state.revision == 22 and
            len(ops) == len(records) == 22 and
            [r.revision for r in records] == list(range(1, 23)) and
            ops[2]['match_id'] == 1994 and
            ops[2]['request_id'] == _LEGACY_76_ORIGINAL):
        return False
    for index, (op, stored) in enumerate(zip(ops, records), 1):
        expected_id = _LEGACY_76_RECOVERED if index == 3 else op['request_id']
        if (stored.request_id != expected_id or
                stored.origin != 'offline' or
                stored.payload_sha256 != _legacy_digest(op, request_id=expected_id)):
            return False
    # Extra check for the exceptional recovered operation, because its
    # request_id differs from the user's current JSON file.
    match = db.session.get(Match, 1994)
    if (match is None or match.tournament_id != tid or
            match.group_id != 357 or not match.is_finished or
            (match.player_a_id, match.player_b_id) != (1131, 1132)):
        return False
    saved_sets = db.session.query(MatchResults).filter_by(match_id=1994).order_by(MatchResults.set_number).all()
    if [[r.score_a, r.score_b] for r in saved_sets] != ops[2]['sets']:
        return False
    return True


def _tree_round(tree, round_number):
    """JSON round keys can be strings on disk or integers in memory."""
    rounds = tree.get('rounds') if isinstance(tree, dict) else None
    if not isinstance(rounds, dict):
        return None
    value = rounds.get(str(round_number))
    return value if value is not None else rounds.get(round_number)


def _resolve(tid, row, used):
    """Resolve an offline match without guessing among equally valid candidates.

    The two narrowly scoped tournament-76 mappings below retain the tested
    historical batch behavior. Other ambiguous matches are rejected until the
    offline format supplies an explicit bracket/round/slot identifier.
    """
    if row['kind'] == 'group':
        match = db.session.get(Match, row['match_id'])
        if (match is None or match.tournament_id != tid or
                match.group_id != row['group_id'] or match.bracket_id is not None or
                match.is_finished or match.id in used or
                (match.player_a_id, match.player_b_id) !=
                (row['player_a_id'], row['player_b_id'])):
            raise SyncStop(f'Skupinový zápas {row["match_id"]} neodpovídá serveru.')
        return match, None

    candidates = (db.session.query(Match, Bracket)
                  .join(Bracket, Match.bracket_id == Bracket.id)
                  .filter(Match.tournament_id == tid, Bracket.tournament_id == tid,
                          Bracket.is_consolation == row['is_consolation'],
                          Bracket.bracket_type == row['bracket_type'],
                          Match.player_a_id == row['player_a_id'],
                          Match.player_b_id == row['player_b_id'],
                          Match.is_finished.is_(False))
                  .all())
    candidates = [(m, b) for m, b in candidates if m.id not in used]

    if len(candidates) == 1:
        return candidates[0]

    # Historical tournament-76 batch: identify a unique, verified tree slot.
    # Do not generalize this based solely on player IDs: placement and main
    # matches can contain the same pair of players.
    expected = {
        2012: ((1123, 1130), 'main_semifinal'),
        2013: ((1128, 1134), 'first_5_8_placement'),
    }
    offline_mid = row['match_id']
    if (tid == 76 and len(candidates) > 1 and offline_mid in expected and
            row['is_consolation'] is False and
            row['bracket_type'] == 'elimination' and
            (row['player_a_id'], row['player_b_id']) == expected[offline_mid][0]):
        chosen = []
        for match, bracket in candidates:
            if bracket.id != 121 or bracket.is_consolation:
                continue
            tree = bracket.tree_data or {}
            if offline_mid == 2012:
                round_two = _tree_round(tree, 2)
                slot = round_two[0] if isinstance(round_two, list) and round_two else None
            else:
                placements = tree.get('placement_rounds') if isinstance(tree, dict) else None
                placement = placements.get('5-8') if isinstance(placements, dict) else None
                slots = placement.get('matches') if isinstance(placement, dict) else None
                slot = slots[0] if isinstance(slots, list) and slots else None
            if type(slot) is int and slot == match.id:
                chosen.append((match, bracket))
        if len(chosen) == 1:
            return chosen[0]

    raise SyncStop(
        f'Offline zápas {offline_mid}: nalezeno {len(candidates)} možných shod; '
        'nelze bezpečně určit pozici v pavouku.',
        409, 'AMBIGUOUS_MATCH'
    )


@stage_sync_bp.errorhandler(SyncStop)
def _sync_error(exc):
    db.session.rollback()
    return jsonify({'status': 'ERROR', 'code': exc.code, 'message': str(exc)}), exc.status


@stage_sync_bp.get('/<int:tid>/handshake')
def handshake(tid):
    _check_environment()
    _authorize(tid)
    state = db.session.get(TournamentSyncState, tid)
    return jsonify({'status': 'OK', 'tournament_id': tid, 'revision': state.revision if state else 0})


@stage_sync_bp.post('/<int:tid>/sync')
def sync(tid):
    _check_environment()
    # Same-origin JSON only. Do not enable CORS for this endpoint.
    origin = request.headers.get('Origin')
    if (request.headers.get('X-Offline-Sync') != '1' or not request.is_json or
            (origin and urlsplit(origin).netloc != request.host)):
        raise SyncStop('Požadavek musí přijít ze stejného webu.', 403, 'ORIGIN')
    if request.content_length is None or request.content_length > 512 * 1024:
        raise SyncStop('Příliš velká nebo neznámá dávka.', 413, 'TOO_LARGE')
    _authorize(tid)
    body = request.get_json(silent=True)
    ops, catalog = _parse_batch(body, tid)
    revision = body['base_revision']
    used = set()

    with atomic_sync_update():
        db.session.execute(
            text('SELECT id FROM tournaments WHERE id=:tid FOR UPDATE'),
            {'tid': tid}
        ).scalar_one()
        _authorize(tid)
        state = db.session.get(TournamentSyncState, tid)
        if state is None:
            state = TournamentSyncState(tournament_id=tid, revision=0)
            db.session.add(state)
            db.session.flush()

        ledger = (db.session.query(TournamentSyncRequest)
                  .filter_by(tournament_id=tid)
                  .order_by(TournamentSyncRequest.revision).all())
        old = {r.request_id: r for r in ledger}
        digests = {
            op['request_id']: hashlib.sha256(
                _canonical({'op': op, 'match': catalog[op['match_id']]}).encode('utf-8')
            ).hexdigest()
            for op in ops
        }
        if (len(ledger) == len(ops) and
                all(op['request_id'] in old and
                    old[op['request_id']].payload_sha256 == digests[op['request_id']]
                    for op in ops)):
            return jsonify({'status': 'ALREADY_SYNCED', 'tournament_id': tid,
                            'revision': state.revision,
                            'confirmed_request_ids': [op['request_id'] for op in ops]})
        if _recognize_legacy_76(tid, revision, ops, ledger, state):
            return jsonify({'status': 'ALREADY_SYNCED', 'tournament_id': tid,
                            'revision': state.revision,
                            'confirmed_request_ids': [op['request_id'] for op in ops]})
        if ledger:
            raise SyncStop(
                'Server již obsahuje synchronizované operace, ale nelze '
                'bezpečně ověřit totožnost dávky.', 409, 'LEDGER_CONFLICT'
            )
        if state.revision != revision:
            raise SyncStop(
                f'Server má revizi {state.revision}, telefon vychází z {revision}.',
                409, 'STALE_REVISION'
            )

        manager = WebManager(tid)
        for index, op in enumerate(ops, 1):
            mid = op['match_id']
            match, bracket = _resolve(tid, catalog[mid], used)
            used.add(match.id)
            server_mid = match.id

            if bracket is not None and bracket.bracket_type == 'round_robin':
                with atomic_result_update():
                    finished = evaluate(
                        server_mid,
                        [str(a) for a, b in op['sets']],
                        [str(b) for a, b in op['sets']]
                    )
                    if not finished:
                        raise SyncStop(f'Operace {index}: minitabulka odmítla skóre.')
                    manager.group_manager.handle_match_completion(
                        server_mid, manager.tournament
                    )
            else:
                form = MultiDict(
                    [('action', 'submit_result'), ('match_id', str(server_mid))] +
                    [('game_a[]', str(a)) for a, b in op['sets']] +
                    [('game_b[]', str(b)) for a, b in op['sets']]
                )
                manager.process_match_action(
                    form, is_playoff=bracket is not None,
                    is_consolation=bool(bracket and bracket.is_consolation)
                )

            db.session.flush()
            if not db.session.get(Match, server_mid).is_finished:
                raise SyncStop(f'Operace {index}: zápas nebyl dokončen.')
            state.revision += 1
            db.session.add(TournamentSyncRequest(
                tournament_id=tid, request_id=op['request_id'],
                payload_sha256=digests[op['request_id']],
                origin='offline', revision=state.revision
            ))

            # Essential for long batches: clear stale SQLAlchemy identity-map
            # state between results, retaining the single outer transaction.
            db.session.flush()
            db.session.expire_all()

        db.session.flush()
        result_revision = state.revision

    return jsonify({'status': 'COMMITTED', 'tournament_id': tid,
                    'revision': result_revision,
                    'confirmed_request_ids': [op['request_id'] for op in ops]})
