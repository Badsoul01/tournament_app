"""Read-only recent tournament participant catalog for the offline PWA (staging only)."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify

from app.models.models import Player, Tournament, db

player_catalog_bp = Blueprint("offline_player_catalog", __name__)


@player_catalog_bp.get("/api/offline/player-catalog")
def recent_player_catalog():
    # Public read-only catalog: no organizer login or organizer-specific filter.
    # Only finished tournaments from the last 120 days are included.
    cutoff = datetime.now() - timedelta(days=120)
    recent = (db.session.query(Tournament)
              .filter(Tournament.is_finished.is_(True),
                      Tournament.date >= cutoff)
              .order_by(Tournament.date.desc(), Tournament.id.desc())
              .limit(8).all())
    result = []
    for tournament in recent:
        players = (db.session.query(Player.name)
                   .filter(Player.tournament_id == tournament.id)
                   .order_by(Player.id).all())
        unique = list(dict.fromkeys(name.strip() for (name,) in players if name and name.strip()))
        result.append({
            "id": tournament.id,
            "name": tournament.name,
            "dateLabel": tournament.date.strftime("%d.%m.%Y") if tournament.date else "",
            "players": unique,
        })

    response = jsonify({
        "format": "spravaturnaje-player-catalog-v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tournaments": result,
    })
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
