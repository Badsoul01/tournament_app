import os
from flask import Flask
from dotenv import load_dotenv
from flask_migrate import Migrate
from app.web import main_bp
from app.models.models import db

migrate = Migrate()

def create_app():
    load_dotenv()
    app = Flask(__name__)

    app.secret_key = os.environ.get("SECRET_KEY", "zalozni_tajny_kod")
    db_url = os.environ.get("DATABASE_URL")

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Inicializace rozšíření
    db.init_app(app)
    migrate.init_app(app, db)

    # Registrace rout/blueprintů

    app.register_blueprint(main_bp)

    # Staging-only offline sync. Production never registers this API.
    if os.environ.get("OFFLINE_SYNC_STAGING") == "1":
        from app.services.tournament.offline_sync_stage import stage_sync_bp
        app.register_blueprint(stage_sync_bp)

        # Staging-only import of NEW tournaments created entirely offline.
        from app.services.tournament.offline_local_import_stage import local_import_bp
        app.register_blueprint(local_import_bp)

        from app.web.offline_pwa_routes import offline_pwa_bp
        app.register_blueprint(offline_pwa_bp)

        from app.web.offline_player_catalog_routes import player_catalog_bp
        app.register_blueprint(player_catalog_bp)
    return app