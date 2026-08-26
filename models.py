from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Tournament(db.Model):
    __tablename__ = "tournaments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, default=lambda: datetime.now().date())
    group_match_format = db.Column(db.Integer)
    playoff_match_format= db.Column(db.Integer)
    advance_per_group = db.Column(db.Integer)  # Stačí nám číslo
    group_elimination_action = db.Column(db.String(50))
    playoff_elimination_action = db.Column(db.String(50))


    has_consolation = db.Column(db.Boolean, default=True)
    consolation_format = db.Column(db.String(50))

    is_finished = db.Column(db.Boolean, default=False)

    # Cizí klíč na celkového vítěze
    winner_id = db.Column(db.Integer, db.ForeignKey("players.id", use_alter=True, name="fk_tournament_winner"), nullable=True)

    # Virtuální vazby (relationsships) - tyto nevytváří sloupce, usnadnují práci v pythonu
    # Například "turnaj.players" vytvoří rovnou seznam všech jeho hráčů
    players = db.relationship("Player",backref="tournament", lazy="dynamic",foreign_keys="Player.tournament_id")
    groups = db.relationship("Group", backref="tournament", lazy="dynamic")
    matches = db.relationship("Match",backref="tournament",lazy="dynamic")
    brackets = db.relationship("Bracket", backref="tournament",lazy="dynamic")

class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable= False)
    is_consolation = db.Column(db.Boolean, default=False)
    is_finished = db.Column(db.Boolean, default=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)



    players = db.relationship("Player", backref="group", lazy="dynamic")
    matches = db.relationship("Match", backref="group", lazy="dynamic")

class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    group_seed = db.Column(db.String(10), nullable=True)

    # Cizí klíče udavající příslušnost k fázím turnaje
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)


class Match(db.Model):
    __tablename__= "matches"

    __table_args__ = (
        db.CheckConstraint(
            '(group_id IS NOT NULL AND bracket_id IS NULL) OR (group_id IS NULL AND bracket_id IS NOT NULL)',
            name='check_match_belongs_to_exactly_one_place'
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    match_type = db.Column(db.String(20), nullable=False)
    match_format= db.Column(db.String(50))

    # údaje pro statistiky
    score_a = db.Column(db.Integer, default=0)
    score_b = db.Column(db.Integer, default=0)
    sets_data = db.Column(db.String(200), nullable=True)


    is_finished = db.Column(db.Boolean,default=False)
    is_in_progress = db.Column(db.Boolean, default=False)

    # Kam zápas patří
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"))
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    bracket_id = db.Column(db.Integer, db.ForeignKey("brackets.id"), nullable=True)

    # hráči v zápase
    player_a_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)
    player_b_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)
    winner_id = db.Column(db.Integer,db.ForeignKey("players.id"), nullable=True)

    player_a = db.relationship("Player", foreign_keys=[player_a_id])
    player_b = db.relationship("Player", foreign_keys=[player_b_id])
    winner = db.relationship("Player", foreign_keys= [winner_id])

class PlayerStats(db.Model):
    __tablename__ = "player_stats"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    stage_name = db.Column(db.String(50),nullable=False)

    points= db.Column(db.Integer, default=0)
    games_win = db.Column(db.Integer, default=0)
    games_lost = db.Column(db.Integer, default=0)
    balls_win = db.Column(db.Integer, default=0)
    balls_lost = db.Column(db.Integer, default=0)

    final_rank = db.Column(db.Integer, nullable=True)


    player = db.relationship("Player", backref=db.backref("stats_records", lazy=True))


class Bracket(db.Model):
    __tablename__ = "brackets"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)

    name = db.Column(db.String(50))  # např. "Hlavní Playoff", "Útěcha - Pavouk", "Útěcha - Skupina"
    bracket_type = db.Column(db.String(50))  # "elimination" (pavouk) nebo "round_robin" (skupina)
    is_consolation = db.Column(db.Boolean, default=False)

    # Např: {"round_1": [{"match_id": 1, "position": 1}, ...]}
    tree_data = db.Column(db.JSON, nullable=True)

    # Relace na zápasy, které do tohoto pavouka patří
    matches = db.relationship("Match", backref="bracket", lazy="dynamic")