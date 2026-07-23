class Results:
    """
    Třída zodpovědná za zpracování statistik, výpočty tabulek,
    vyhodnocení skupin a sestavení konečného pořadí turnaje.
    """

    def __init__(self):
        self.ranking = []
        self.qualified_players = []
        self.eliminated_players = []

    def compute_final_ranking(self, tournament_branches):
        """
        Sestaví a vrátí seřazený seznam slovníků s konečným umístěním hráčů
        na základě stavu hlavní větve playoff a dohrávkových pavouků.
        """
        self.ranking = []
        main_p= tournament_branches.get("main")

        # Zpracování 1. a 2.místa z hlavní větve playoff
        if main_p and main_p.winner:
            self.ranking.append({"name":main_p.winner.name,"place":"1"})

            #Bezpečné získání posledního kola a finalového zápasu
            if main_p.rounds:
                last_round_num = max(main_p.rounds.keys())
                final_matches = main_p.rounds[last_round_num]

                if final_matches:
                    final_match = final_matches[0]
                    # poražený ve finále bere 2.místo
                    finalist = final_match.player_B if final_match.winner == final_match.player_A else final_match.player_A
                    self.ranking.append({"name":finalist.name,"place":"2"})

        # Zpracování pozic z dohrávkových pavouků podle klíčů (např. "3", "5.-8.")
        placement_branch = tournament_branches.get("placement", {})
        sorted_keys = sorted(placement_branch.keys(), key=lambda k: int(k.split("-")[0]))

        for key in sorted_keys:
            p = placement_branch[key]
            if p.winner:
                self.ranking.append({"name":p.winner.name,"place":key})

        return self.ranking


    def are_groups_finished(self,group_stage):
        """
        Zkontroluje, zda jsou všcehny zápasy ve všech skupinách odehrané.
        """
        for group_name,group_obj in group_stage.groups.items():
            for match in group_obj.matches:
                if not match.is_finished:
                    return False
        return True

    def evaluate_group_stage(self,group_stage,advance_per_group):
        """
        sestaví seznam postupujících hráčů ze skupin na základě jejich umístění
        (např top 2 z každé skupiny) pro vstup do playoff.
        """
        qualified = []
        eliminated = []

        for group_name in sorted(group_stage.groups.keys()):
            # Získáme seřazené hráče v dané skupině
            ranked_players = group_stage.rank_players(group_name)

            # Vybereme daný počet postupujících z vrcholu tabulky
            top_players = ranked_players[:advance_per_group]
            bottom_players = ranked_players[advance_per_group:]

            # Zpracování postupujícíchě
            for rank,player in enumerate(top_players,start=1):
                player.group_name = group_name
                player.group_rank = rank
                qualified.append(player)

            # Zpracování vyřazených
            for rank,player in enumerate(bottom_players, start=advance_per_group+1):
                player.group_name= group_name
                player.group_rank= rank
                eliminated.append(player)

        self.qualified_players =  qualified
        self.eliminated_players = eliminated

        return self.qualified_players, self.eliminated_players




