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
        podle jejich statistik, včetně vyřešení minitabulek při shodě bodů.
        """
        players = self.groups[group_name]

        # 1. Celkové seřazení hráčů podle standartních globálních statistik (body, sety, míčky)
        sorted_players = sorted(
            players,
            key=lambda p:(
                p.get_sorting_stats(stage_name=self.stage_name)
            ),
            reverse=True
        )

        matches = self.group_matches.get(group_name, [])
        final_ranked = []

        # 2.  Sestkupení hráčů, kteří mají shodné primární kritérium (body = první prvek n-tice)
        # itertools.groupby vyžaduje seřazená data, což sorted_players splňují.
        for points_key, group_iter in itertools.groupby(
            sorted_players,
            key=lambda p: p.get_sorting_stats(stage_name=self.stage_name)[:1]
        ):
            subgroup = list(group_iter)

            # Pokud je ve skupince jen 1 hráč, nemá s kým řešit shodu bodů
            if len(subgroup) == 1:
                final_ranked.extend(subgroup)
            else:
                # Pokud je hráčů více se stejnými body, aplikujeme minitabulku
                resolved_subgroup = self._resolve_mini_group(subgroup=subgroup, matches=matches)
                final_ranked.extend(resolved_subgroup)

        return final_ranked

    def are_all_matches_played(self,group_name: str) -> bool:
        """
        Vratí True,pokud jsou všechny zápasy ve skupině dohrané,
        jinak vrací False.
        """
        return all(match.is_finished for match in self.group_matches[group_name])

    def _resolve_mini_group(self,subgroup: list[Player], matches: list) -> list[Player]:
        """
        Vytvoří a vyhodnotí minitabulku ze vzájemných zápasů pro hráče
        se stejným počtem bodů.
        """
        subgroup_set = set(subgroup)

        # 1. Vyfiltrujeme pouze zápasy odehrané POUZE mezi členy této podskupiny, které jsou dohrané
        relevant_matches = [
            m for m in matches
            if m.is_finished and m.player_A in subgroup_set and m.player_B in subgroup_set
        ]
        # Pokud neexistují vzájemné zápasy pro každého hráče v podskupině
        if not relevant_matches:
            return subgroup


        #  Inicializace mini-statistik pro každého hráče v podskupině
        mini_stats = {p: {"points": 0,"game_diff": 0, "ball_diff": 0} for p in subgroup}

        for match in relevant_matches:
            pA = match.player_A
            pB = match.player_B

            games_a_win = 0
            games_b_win = 0
            balls_a_total = 0
            balls_b_total = 0

            for balls_a, balls_b in match.played_sets:
                balls_a_total += balls_a
                balls_b_total += balls_b

                if balls_a > balls_b:
                    games_a_win += 1
                else:
                    games_b_win += 1

            # Přičtení setových a míčkových rozdílů
            mini_stats[pA]["game_diff"] += (games_a_win - games_b_win)
            mini_stats[pB]["game_diff"] += (games_b_win - games_a_win)

            mini_stats[pA]["ball_diff"] += (balls_a_total - balls_b_total)
            mini_stats[pB]["ball_diff"] += (balls_b_total - balls_a_total)

            if games_a_win > games_b_win:
                mini_stats[pA]["points"] += 3
            elif games_a_win == games_b_win:
                mini_stats[pA]["points"] += 1
                mini_stats[pB]["points"] += 1
            else:
                mini_stats[pB]["points"] += 3

        # 3.Seřazení podskupiny podle mini-statistik
        sorted_subgroup = sorted(
            subgroup,
            key=lambda p: (
                mini_stats[p]["points"],
                mini_stats[p]["game_diff"],
                mini_stats[p]["ball_diff"]
            ),
            reverse=True
        )

        return sorted_subgroup