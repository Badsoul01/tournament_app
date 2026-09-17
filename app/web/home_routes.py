
from flask import render_template
from .blueprint import main_bp
from app.models.models import Tournament as TournamentModel

@main_bp.route("/")
def home():
    active_tournaments = TournamentModel.query.filter_by(is_finished=False).order_by(TournamentModel.date.desc()).all()
    return render_template("index.html", active_tournaments=active_tournaments)