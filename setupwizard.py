from bs4 import BeautifulSoup
import requests
from datetime import date
from config import RULES_OPTIONS

class SetupWizard:

    def __init__(self):
        #základní informace
        self.name = ""
        self.date = date.today().strftime("%Y-%m-%d")
        self.total_groups = RULES_OPTIONS["total_groups_count"][0]
        self.players = []

        #formát zápasů
        self.group_match_format = "2"
        self.playoff_match_format = "BO3"

        #pravidla postupu
        self.advancing_per_group = RULES_OPTIONS["advance_per_group"][0]
        self.players_per_group_limit = RULES_OPTIONS["players_per_group_limit"][0]

        #akce
        self.non_advancing_action = "playoff_b"
        self.playoff_losers_action = "consolation"

