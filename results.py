from group import Group

class Results:
    """
    Třída zodpovědná za zpracování statistik, výpočty tabulek,
    vyhodnocení skupin a sestavení konečného pořadí turnaje.
    """

    def __init__(self)-> None:
        # Seznam pro uložení celkového konečného pořadí hráčů v turnaji
        self.ranking: list[dict]= []
        # Seznam postupujících hráčů
        self.qualified_players: list = []
        # Seznam vyřazených hráčů
        self.eliminated_players: list = []

    def compute_final_ranking(self, tournament_branches: dict) -> list[dict]:
        """
        Sestaví a vrátí seřazený seznam slovníků s konečným umístěním hráčů
        na základě stavu hlavní větve playoff a dohrávkových pavouků.
        """
        self.ranking = []
        main_p= tournament_branches.get("main")
        print(f"DEBUG RESULTS: Přijaté branches: {list(tournament_branches.keys()) if tournament_branches else 'Je prázdné!'}")


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
        placement_branch = main_p.placement_rounds if main_p else {}
        print(f"DEBUG RESULTS: Obsah placement_branch: {list(placement_branch.keys())}")
        sorted_keys = sorted(placement_branch.keys(), key=lambda k: int(k.split("-")[0]))


        for key in sorted_keys:
            bracket_data = placement_branch[key]
            matches = bracket_data.get("matches", [])

            parts = key.split("-")
            # Zjistíme, jeslti klíč představuje přesně dvě sousední pozice (např. 3,4)
            if len(parts) == 2 and len(matches) == 1:
                match = matches[0]
                print(f"DEBUG RESULTS: Zápas pro '{key}' - hotovo: {match.is_finished}, vítěz: {match.winner}")

                if match.is_finished and match.winner:
                    winner = match.winner
                    loser = match.player_B if match.winner == match.player_A else match.player_A

                    self.ranking.append({"name": winner.name, "place": parts[0]})
                    if loser:
                        self.ranking.append({"name": loser.name, "place": parts[1]})
            else:
                print(f"DEBUG RESULTS: Klíč '{key}' nesplnil podmínku (parts={len(parts)}, matches={len(matches)})")

        print(f"DEBUG RESULTS: Výsledný ranking: {self.ranking}")
        return self.ranking


    def are_groups_finished(self,group_stage) -> bool:
        """
        Zkontroluje, zda jsou všcehny zápasy ve všech skupinách odehrané.
        """
        return all(
            match.is_finished
            for match_list in group_stage.group_matches.values()
            for match in match_list
        )

    def evaluate_group_stage(self,group_stage: Group, advance_per_group:int) -> tuple[list]:
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




