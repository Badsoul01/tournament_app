# Nejdřív načteme prázdný blueprint
from .blueprint import main_bp

# Pak načteme soubory s routami, čímž se routy "přilepí" na main_bp
from . import home_routes
from . import stats_routes
from . import settings_routes
from . import log_routes
from . import tournament_routes