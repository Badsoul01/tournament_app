STATE_OF_WIZARD= ["tournament_rules","groups_rules","playoff_rules"]

TOURNAMENT_RULES= {
    "available_formats": {
        "groups_and_playoff": "skupiny a playoff",
        "group": "skupina",
        "playoff": "playoff"
    },
}

GROUPS_RULES = {
    "group_match_format": {
        2: "2 hrané sety",
        3: "2 vítězné sety",
        5: "3 vítězné sety"
        },
    "min_players_per_group": 1,
    "max_players_per_group": 10,
    "min_group": 1,
    "max_group": 1 if TOURNAMENT_RULES["available_formats"]== "group" else  26,
    "group_creation_options":[1,2,4,6],
    "min_advance_per_group": 1,
    "max_advance_per_group": 4,
    "advance_per_group":[1,2,3,4],
    "elimination_actions": {
        "playoff_b": "Playoff B",
        "minigroup": "Mini-skupina o pořadí",
        "KO": "Konec v turnaji"
    },

}

PLAYOFF_RULES = {
    "playoff_match_format":{
        3: "2 vítězné sety",
        5: "3 vítězné sety",
        7: "4 vítězné sety"
                    },
    "elimination_actions": {
        "consolation":"Dohrávka o pořadí",
        "KO": "Konec v turnaji"
        }

}