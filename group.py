import itertools

from player import Player
from match import Match


class Group:
    """
    Třída zodpovědná za správu skupinové fáze turnaje.
    Uchovává strukturu skupin, generuje vzájemné zápasy mezi hráči,
    zajištuje řazení hráčů podle statistik a kontroluje dohranost skupin.
    """

    def __init__(self,groups_dict: dict,match_format: str,stage_name: str):
        self.stage_name = stage_name
         # Slovník skupin, kde klíč je název skupiny a hodnota je seznam objektů hráčů
        self.groups = groups_dict
        #formát zápasů ve skupinách
        self.match_format = match_format
        # Slovník pro uchování vygenerovaných zápasů pro každou skupinu zvlášť.
        self.group_matches = {key:[] for key in self.groups.keys()}


    def generate_matches(self,tournament)-> None:
        """
        Vygeneruje zápasy pro všechny skupiny systémem každý s každým.
        Vytvoří instance zápasů, přiřadí jim unikátní ID z turnaje a chytře je proháže tak,
        aby stejný hráč nehrál hned v následujícím zápase.
        """
        for group_name, players in self.groups.items():
            pool = []
            # Projdeme všechny unikátní dvojice hráčů v dané skupině
            for player_a, player_b in itertools.combinations(players,2):
                pool.append(Match(player_a=player_a,
                                     player_b=player_b,
                                     match_format=self.match_format,
                                     tournament_stage=self.stage_name,
                                     match_id=tournament.get_next_match_id()
                                     ))

            # Chytré proházení zápasů (spacing), aby hráči nehráli dvakrát za sebou.
            ordered_matches = []
            while pool:
                # Zkusíme najít zápas, ve kterém nehraje nikdo z předchozího zápasu.
                next_match_idx = 0
                if ordered_matches:
                    last_match = ordered_matches[-1]
                    last_players = {last_match.player_A, last_match.player_B}

                    # hledáme první vhodný zápas, kde se neopakuje žádný hráč
                    for i, match in enumerate(pool):
                        if match.player_A not in last_players and match.player_B not in last_players:
                            next_match_idx = i
                            break

                chosen_match = pool.pop(next_match_idx)
                ordered_matches.append(chosen_match)


            self.group_matches[group_name]= ordered_matches


    def rank_players(self,group_name: str) -> list[Player]:
        """
        Vrátí seřazený seznam hráčů v dané skupině sestupně
        podle jejich statistik pro aktuální fázi turnaje.
        """
        players = self.groups[group_name]

        sorted_players = sorted(
            players,
            key=lambda p:(
                p.get_sorting_stats(stage_name=self.stage_name)
            ),
            reverse=True
        )

        return sorted_players

    def are_all_matches_played(self,group_name: str) -> bool:
        """
        Vratí True,pokud jsou všechny zápasy ve skupině dohrané,
        jinak vrací False.
        """
        return all(match.is_finished for match in self.group_matches[group_name])