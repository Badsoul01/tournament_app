RULES_OPTIONS = {
    #počet skupin
    "total_groups_count":[1,2,3,4,5,6,7,8],

    #formát zápasů
    "group_match_format": {"2": "2 sets",
                     "BO3": "Best of 3",
                     "BO5": "Best of 5"
                    },
    "playoff_match_format":{
        "BO3": "Best of 3",
        "BO5": "Best of 5"
        },

    #pravidla pro postup a vyřazování
    "advance_per_group":[1,2,3,4],
    "players_per_group_limit":[4,5,6],



    "non_advancing_action": {
        "playoff_b": "Postup do pavouka B",
        "minigroup": "Mini-skupina o pořadí",
        "KO": "Konec v turnaji"
    },
    "playoff_losers_action":{
        "consolation":"Turnaj útěchy",
        "KO": "Konec v turnaji"

    }
}
