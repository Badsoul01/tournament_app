class Tournament:

    def __init__(self,name:str,groups_data_from_web:dict,settings_from_web:dict):
        self.name = name
        self.raw_groups_data = groups_data_from_web

        #---- Pravidla ----

        #Formáty zápasů
        self.group_match_format = settings_from_web.get("group_match_format","2 sets")
        self.playoff_match_format = settings_from_web.get("playoff_match_format","Best of 3")
        #pravidla pro postup a vyřazení
        self.advancing_per_group = settings_from_web.get("advancing_per_group",2)
        self.non_advancing_action = settings_from_web.get("non_advancing_action","KO")
        self.players_lossers_action = settings_from_web.get("players_lossers_action","KO")

        # ---- Objekty ----

        #1. základní skupina
        self.groups = []
        #2. hlavní vyřazovací část
        self.main_playoff = None
        #3. Útěcha
        self.consolation_playoff = []
        self.consolation_groups = []
        #4.dohrávka o umístění
        self.placement_playoff = {}

