STATE_OF_WIZARD= ["tournament_rules","groups_rules","playoff_rules"]

GROUPS_RULES = {
    "group_match_format": {
        2: "2 hrané sety",
        3: "2 vítězné sety",
        5: "3 vítězné sety"
        },
    "min_players_per_group": 3,

    "max_players_per_group": 8,
    "min_group": 1,
    "max_group": 8,
    "group_creation_options":[1,2,3,4,5,6,7,8],
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
    "players_allowed_to_playoff" : [6,7,8,12,13,14,15,16,25,26,27,28,29,30,31,32],
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
# PLAYOFF STRUTRURA

starter_edition = {
    8 : [0,1,2,3],
    "8_reverse" : [3,2,1,0],
    8_1 : ["BYE_idx",1,2,3],
    "8_1_reverse" : [3,2,1,"BYE_idx"],
    8_2 : ["BYE_idx",1,2,"BYE_idx"],
    "8_2_reverse": ["BYE_idx",2,1,"BYE_idx"]
}

classic_edition = {
    16 : starter_edition[8]+ starter_edition["8_reverse"],
    16_1: starter_edition["8_1_reverse"] + starter_edition["8_reverse"],
    16_2: starter_edition[8_1] + starter_edition["8_1_reverse"],
    16_4: starter_edition[8_2] + starter_edition["8_2_reverse"]
}

moderate_edition = {
    32 : classic_edition[16] *2 *2,
    32_4: classic_edition[16_2]*2*2

}