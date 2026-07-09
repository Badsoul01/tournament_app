import random
import itertools
from player import Player
from match import Match


class Group:

    def __init__(self,groups_dict:dict,match_format:str):
        self.tournament_stage = "Group"
        self.groups = groups_dict
        self.match_format = match_format
        self.group_matches = {key:[] for key in self.groups.keys()}


    def generate_matches(self):

        for group_name, players in self.groups.items():
            matches = []
            for player_a, player_b in itertools.combinations(players,2):
                matches.append(Match(player_a=player_a,player_b=player_b,match_format=self.match_format,tournament_stage=self.tournament_stage))

            random.shuffle(matches)
            self.group_matches[group_name]= matches

    def rank_players(self,group_name):
        players = self.groups[group_name]

        sorted_players = sorted(
            players,
            key=lambda p:(
                p.group["points"],
                p.difference_of_score("Group")["Games"],
                p.difference_of_score("Group")["Balls"]
            ),
            reverse=True
        )

        return sorted_players


    def are_all_matches_played(self,group_name):
        """Vratí True,pokud jsou všechny zápasy ve skupině dohrané."""
        return all(match.is_finished for match in self.group_matches[group_name])