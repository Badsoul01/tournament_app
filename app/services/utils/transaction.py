"""Volitelné řízení jediné transakce při ukládání výsledku.

Běžné volání atomic_result_update() zůstává beze změny: samo commitne.
Synchronizace může použít atomic_sync_update() jako nadřazený kontext;
commit pak proběhne až na jeho konci.

POZOR: platí jen pro kód používající tuto db.session a nevolající
přímo commit() uvnitř engine. Před integrací je nutný audit těchto míst.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from app.models.models import db

_atomic_result = ContextVar("atomic_tournament_result", default=False)
_atomic_sync = ContextVar("atomic_tournament_sync", default=False)


def commit_or_flush():
    """Během výsledku/synchronizace flush, jinak původní commit."""
    if _atomic_result.get() or _atomic_sync.get():
        db.session.flush()
    else:
        db.session.commit()


@contextmanager
def atomic_sync_update():
    """Nadřazený commit výsledků + revize; používat jen na jedné db.session."""
    if _atomic_sync.get() or _atomic_result.get():
        raise RuntimeError("Vnořená synchronizační transakce není podporována.")
    token = _atomic_sync.set(True)
    try:
        yield
        db.session.flush()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        _atomic_sync.reset(token)


@contextmanager
def atomic_result_update():
    if _atomic_result.get():
        raise RuntimeError("Vnořená transakce výsledku není podporována.")
    token = _atomic_result.set(True)
    try:
        yield
        db.session.flush()
        if not _atomic_sync.get():
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        _atomic_result.reset(token)
