from group import Group
from match import Match
from playoff import Playoff


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
        na základě stavu hlavní větve playoff, dohrávkových pavouků a útěchy.
        """
        self.ranking = []

        print(f"DEBUG RESULTS: Přijaté branches: {list(tournament_branches.keys()) if tournament_branches else 'Je prázdné!'}")

        # ==========================================
        # 1. ZPRACOVÁNÍ HLAVNÍ VĚTVE
        # ==========================================
        main_p = tournament_branches.get("main")
        # Zpracování 1. a 2.místa z hlavní větve playoff
        if main_p:
            self._extract_playoff_results(playoff_branch= main_p, offset=0)

        if self.ranking:
            current_offset = max(int(item["place"]) for item in self.ranking)
        else:
            current_offset = 0

        # ==========================================
        # 2. ZPRACOVÁNÍ ÚTĚCHY (Consolation)
        # ==========================================

        consolation = tournament_branches.get("consolation")
        if consolation:
            if isinstance(consolation, Group):
                self._extract_group_results(group_branch=consolation,offset=current_offset)
            elif isinstance(consolation, Playoff):
                self._extract_playoff_results(playoff_branch=consolation,offset=current_offset)

        print(f"DEBUG RESULTS: Výslední ranking: {self.ranking}")
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

    def _extract_group_results(self,group_branch: Group,offset: int) -> None:
        """
        Pomocná metoda pro extrakci pořadí z Mini-skupiny.
        """
        # Projdeme všechny skupiny


        for group_name in group_branch.groups.keys():
            if group_branch.are_all_matches_played(group_name):
                ranked_players = group_branch.rank_players(group_name=group_name)

                # Zapíšeme je do žebříčku, index 1 znamená vítěz skupiny(přičteme offset)
                valid_index = 1
                for player in ranked_players:
                    if not isinstance(player,str):
                        self.ranking.append({
                            "name": player.name,
                            "place": str(valid_index + offset)
                        })
                        valid_index+=1

    def _extract_playoff_results(self, playoff_branch: Playoff,offset: int) -> None:
        """
        Pomocná metoda, která vyextrahuje pořadí z předaného pavouka.
        Parametr offset zajišťuje, že vítěz playoff B nedostane 1. místo,
        ale naváže na konec hlavního pavouka.
        """

        # Zpracování 1. a 2. místa v daném pavouku
        if playoff_branch and playoff_branch.winner:
            # Přičteme offset k základní pozici
            self.ranking.append({"name": playoff_branch.winner.name, "place": str(1+offset)})

            if playoff_branch.rounds:
                last_round_num = max(playoff_branch.rounds.keys())
                final_matches = playoff_branch.rounds[last_round_num]
                # poražený ve finále bere 2.místo (2 + offset)
                if final_matches:
                    final_match = final_matches[0]
                    finalist = final_match.player_B if final_match.winner == final_match.player_A else final_match.player_A
                    self.ranking.append({"name": finalist.name, "place": str(2 + offset)})

            # Zpracování pozic z dohrávkových pavouků
            placement_branch = playoff_branch.placement_rounds if playoff_branch else {}
            print(f"DEBUG RESULTS: Obsah placement_branch: {list(placement_branch.keys())}")

            sorted_keys = sorted(placement_branch.keys(), key=lambda  k: k.split("-"))

            for key in sorted_keys:
                bracket_data = placement_branch[key]
                matches = bracket_data.get("matches", [])
                parts = key.split("-")

                # Zjistíme, jestli klíč představuje přesně dvě sousední pozice
                if len(parts) == 2 and len(matches) == 1:
                    match = matches[0]
                    if isinstance(match, Match):
                        print(f"DEBUG RESULTS: Zápas pro '{key}' - hotovo: {match.is_finished}, vítěz: {match.winner}")

                        if match.is_finished and match.winner:
                            winner = match.winner
                            loser = match.player_A if match.winner == match.player_B else match.player_B

                            # aplikujeme offset na vyparsovaná čísla
                            place_winner = str(int(parts[0]) + offset)
                            place_loser = str(int(parts[1]) + offset)

                            self.ranking.append({"name": winner.name, "place":place_winner})
                            if loser:
                                self.ranking.append({"name": loser.name, "place": place_loser})

                else:
                    print(f"DEBUG RESULTS: Klíč '{key}' nesplnil podmínku (parts= {len(parts)}, matches={len(matches)})")





