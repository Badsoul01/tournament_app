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

    @classmethod
    def create_from_raw_data(cls,raw_groups_dict: dict, match_format: str, stage_name: str):
        """
        Tovární metoda: Převezme surová data skupin,
        sama vyrobí objekty Player a vrátí hotovou instanci Group.
        """
        transformed_groups_dict = {}
        for group_name, player_names in raw_groups_dict.items():
            player_object = []
            for name in player_names:
                player_object.append(Player(name=name))
            transformed_groups_dict[group_name] = player_object

        return cls(groups_dict=transformed_groups_dict,match_format=match_format,stage_name=stage_name)

    def generate_matches(self,tournament)-> None:
        """
        Vygeneruje zápasy pro všechny skupiny spravedlivou kruhovou metodou (round-robin),
        která zajištuje přirozené pauzy mezi zápasy pro jednotlivé hráče.
        """
        for group_name, players in self.groups.items():
            match_players = list(players)

            # Pokud je lichý počet hráčů, přidáme None (volno /BYE)
            if len(match_players) % 2 != 0:
                match_players.append(None)

            n = len(match_players)
            round_count = n - 1
            half = n // 2

            ordered_matches = []
            # Kruhová metoda generování kol
            for r in range(round_count):
                for i in range(half):
                    player_a = match_players[i]
                    player_b = match_players[n - 1 -i]

                    # Pokud nejde o volno (BYE), vytvoříme reálný Match objekt
                    if player_a is not None and player_b is not None:
                        ordered_matches.append(
                            Match(
                                player_a=player_a,
                                player_b=player_b,
                                match_format= self.match_format,
                                tournament_stage= self.stage_name,
                                match_id=tournament.get_next_match_id()
                            )
                        )
                match_players = [match_players[0]] + [match_players[-1]] + match_players[1:-1]

            self.group_matches[group_name]= ordered_matches


    def rank_players(self,group_name: str) -> list[Player]:
        """
        Vrátí seřazený seznam hráčů v dané skupině sestupně
        podle jejich statistik, včetně vyřešení minitabulek při shodě bodů.
        """
        players = self.groups[group_name]

        # 1. Rozdělení: oddělíme reálné hráče a placeholdery
        real_players = [p for p in players if not isinstance(p, str)]
        placeholders = [p for p in players if isinstance(p, str)]


        # 2. Seřazení: Řadíme pouze reálné hráče (body, sety, míčky)
        sorted_players = sorted(
            real_players,
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

        final_ranked.extend(placeholders)
        return final_ranked

    def are_all_matches_played(self,group_name: str) -> bool:
        """
        Vratí True,pokud jsou všechny zápasy ve skupině dohrané,
        jinak vrací False.
        """
        return all(match.is_finished for match in self.group_matches[group_name])

    def replace_placeholders(self,group_name: str, placeholder: str, real_player) -> None:
        """
        Nahradí textový zástupce (např. "1A") reálným objektem hráče
        ve skupině i ve všech jejich vygenerovaných zápasech.
        """
        players_list = self.groups.get(group_name,[])
        for idx, player_item in enumerate(players_list):
            if player_item == placeholder:
                players_list[idx] = real_player

        matches = self.group_matches.get(group_name,[])
        for match in matches:
            if match.player_A ==  placeholder:
                match.player_A = real_player
            if match.player_B == placeholder:
                match.player_B = real_player

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


