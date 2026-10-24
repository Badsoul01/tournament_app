"""Volitelné řízení jediné transakce při ukládání výsledku."""
from contextlib import contextmanager
from contextvars import ContextVar
from app.models.models import db

_atomic_result = ContextVar("atomic_tournament_result", default=False)


def commit_or_flush():
    """Mimo úpravu výsledku zachová původní commit."""
    if _atomic_result.get():
        db.session.flush()
    else:
        db.session.commit()


@contextmanager
def atomic_result_update():
    if _atomic_result.get():
        raise RuntimeError("Vnořená transakce výsledku není podporována.")
    token = _atomic_result.set(True)
    try:
        yield
        db.session.flush()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        _atomic_result.reset(token)
