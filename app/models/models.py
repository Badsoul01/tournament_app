from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash


db = SQLAlchemy()

class Tournament(db.Model):
    __tablename__ = "tournaments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    group_match_format = db.Column(db.Integer)
    playoff_match_format= db.Column(db.Integer)
    advance_per_group = db.Column(db.Integer)  # Stačí nám číslo
    group_elimination_action = db.Column(db.String(50))
    playoff_elimination_action = db.Column(db.String(50))
    total_players = db.Column(db.Integer, nullable=False)
    total_players_in_playoff = db.Column(db.Integer, default=0)

    has_consolation = db.Column(db.Boolean, default=True)
    consolation_format = db.Column(db.String(50))

    is_finished = db.Column(db.Boolean, default=False)

    # Cizí klíč na celkového vítěze
    winner_id = db.Column(db.Integer, db.ForeignKey("players.id", use_alter=True, name="fk_tournament_winner"), nullable=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey("organizers.id"), nullable=True)

    # Virtuální vazby (relationsships) - tyto nevytváří sloupce, usnadnují práci v pythonu
    # Například "turnaj.players" vytvoří rovnou seznam všech jeho hráčů
    players = db.relationship("Player",backref="tournament", lazy="dynamic",foreign_keys="Player.tournament_id")
    groups = db.relationship("Group", backref="tournament", lazy="dynamic")
    matches = db.relationship("Match",backref="tournament",lazy="dynamic")
    brackets = db.relationship("Bracket", backref="tournament",lazy="dynamic")
    winner = db.relationship("Player", foreign_keys=[winner_id])

    @property
    def consolation_display_name(self):
        if not self.has_consolation:
            return "Nehraje se"

        mapping = {
            "minigroup": "Skupina",
            "playoff_b": "Playoff B",

        }
        # Vrací mapovanou hodnotu, nebo fallback na původní hodnotu / "Nehraje se"
        return mapping.get(self.group_elimination_action, 'Nehraje se')

    @property
    def formatted_date(self):
        if self.date:
            return self.date.strftime('%d.%m.%Y')
        return ""



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

    global_player_id = db.Column(db.Integer, db.ForeignKey("global_players.id"), nullable=True)

class GlobalPlayer(db.Model):
    __tablename__ = "global_players"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable= False)

    # Celkové statistiky
    last_points_gained = db.Column(db.Integer, default=0)
    matches_played = db.Column(db.Integer, default=0)
    matches_won = db.Column(db.Integer, default=0)
    matches_lost = db.Column(db.Integer, default= 0)
    matches_drawn = db.Column(db.Integer, default = 0)

    # Pro sledování průměrného umístění:
    tournaments_played = db.Column(db.Integer, default=0)
    sum_of_ranks = db.Column(db.Integer, default=0)

    last_rank = db.Column(db.Integer, nullable=True)
    last_tournament_date = db.Column(db.Date, nullable=True)

    #Vlastnost
    @property
    def average_rank(self):
        if self.tournaments_played == 0:
            return None
        return  round(self.sum_of_ranks/ self.tournaments_played, 2)

    @property
    def total_points(self):
        """Vrátí součet bodů pouze z turnajů za posledních 365 dní."""
        one_year_ago = datetime.now().date() - timedelta(days=365)

        total = 0
        for entry in self.tournament_entries:  # backref z Player modelu
            if entry.tournament and entry.tournament.is_finished:
                # Převedeme datetime na date, aby porovnání s one_year_ago fungovalo bezchybně
                t_date = entry.tournament.date
                if hasattr(t_date, 'date'):
                    t_date = t_date.date()

                if t_date and t_date >= one_year_ago:
                    p_stats = PlayoffStats.query.filter_by(player_id=entry.id).first()
                    c_stats = ConsolationStats.query.filter_by(player_id=entry.id).first()

                    if p_stats and p_stats.points_gained:
                        total += p_stats.points_gained
                    elif c_stats and hasattr(c_stats, 'points_gained') and c_stats.points_gained:
                        total += c_stats.points_gained

        return total

    tournament_entries = db.relationship("Player", backref="global_profile", lazy="dynamic")


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

    @property
    def formatted_score(self):
        wins_a = 0
        wins_b = 0
        set_details = []

        # Z tabulky MatchResults načteme sety pro tento zápas, seřazené podle pořadí
        for s in self.sets.order_by(MatchResults.set_number).all():
            if s.score_a > s.score_b:
                wins_a += 1
            elif s.score_b > s.score_a:
                wins_b += 1
            set_details.append(f"{s.score_a}:{s.score_b}")

        overall = f"{wins_a} : {wins_b}"

        # Pokud existují detaily setů, přidáme je do závorky
        if set_details:
            return f"{overall} ({', '.join(set_details)})"
        return overall

    @property
    def overall_score(self):
        wins_a = 0
        wins_b = 0
        for s in self.sets.order_by(MatchResults.set_number).all():
            if s.score_a > s.score_b:
                wins_a += 1
            elif s.score_b > s.score_a:
                wins_b += 1
        return f"{wins_a} : {wins_b}"

    @property
    def phase_display_name(self):
        if self.group:
            return self.group.name  # Vrací např. "Skupina A"
        elif self.bracket:
            return self.bracket.name  # Vrací např. "Hlavní Playoff" nebo "Útěcha (Playoff B)"
        return self.match_type  # Fallback

class MatchResults(db.Model):
    __tablename__= "match_results"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    score_a=db.Column(db.Integer, default=0)
    score_b=db.Column(db.Integer, default=0)

    match = db.relationship("Match", backref=db.backref("sets", cascade="all,delete-orphan",lazy="dynamic"))

class GroupStats(db.Model):
    __tablename__ = "group_stats"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)

    points = db.Column(db.Integer, default=0)
    games_win = db.Column(db.Integer, default=0)
    games_lost = db.Column(db.Integer, default=0)
    balls_win = db.Column(db.Integer, default=0)
    balls_lost = db.Column(db.Integer, default=0)

    player = db.relationship("Player", backref=db.backref("group_stats", uselist=False, cascade="all, delete-orphan"))


class PlayoffStats(db.Model):
    __tablename__ = "playoff_stats"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)

    games_win = db.Column(db.Integer, default=0)
    games_lost = db.Column(db.Integer, default=0)
    balls_win = db.Column(db.Integer, default=0)
    balls_lost = db.Column(db.Integer, default=0)

    final_rank = db.Column(db.Integer, nullable=True)
    points_gained = db.Column(db.Integer, default=0)

    player = db.relationship("Player", backref=db.backref("playoff_stats", uselist=False, cascade="all, delete-orphan"))


class ConsolationStats(db.Model):
    __tablename__ = "consolation_stats"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)

    points = db.Column(db.Integer, default=0)
    games_win = db.Column(db.Integer, default=0)
    games_lost = db.Column(db.Integer, default=0)
    balls_win = db.Column(db.Integer, default=0)
    balls_lost = db.Column(db.Integer, default=0)
    final_rank = db.Column(db.Integer, nullable=True)


    player = db.relationship("Player", backref=db.backref("consolation_stats", uselist=False, cascade="all, delete-orphan"))


class Organizer(db.Model):
    __tablename__ = "organizers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    pwd_hash = db.Column(db.String(255), nullable=False)

    # Ukládá datum a čas posledního přihlášení.
    # Při vytvoření účtu se rovnou zapíše aktuální čas.
    last_login = db.Column(db.DateTime, default=datetime.now)

    tournaments = db.relationship("Tournament", backref="organizer", lazy="dynamic")

    def set_password(self, password):
        """Vygeneruje bezpečný hash z textového hesla a uloží ho."""
        self.pwd_hash = generate_password_hash(password)

    def check_password(self, password):
        """Porovná zadané heslo s uloženým hashem a vrátí True/False."""
        return check_password_hash(self.pwd_hash, password)


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