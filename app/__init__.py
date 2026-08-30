import os
from flask import Flask
from dotenv import load_dotenv
from flask_migrate import Migrate
from app.web.routes import main_bp
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

    return app