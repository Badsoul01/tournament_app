class WebManager:
    """
    Tiskový mluvčí.
    Stará se o komunikaci mezi webem(main.py) a logikou turnaje (Tournament)
    Přežvyká data pro HTML šablony a zpracovává akce z formulářů.
    """

    def __init__(self, tournament):
        self.tournament = tournament

    # ==============================
    #  TISKOVÝ MLUVČÍ
    # ==============================

    def get_groups_for_web(self, stage: str = "main") -> dict | None:
        """
        Vrátí slovník skupin a jejich aktuální pořadí ve formátu vhodném pro webové zobrazení.
        Obsahuje už zformátované hráče (statistiky) i zformátované zápasy.
        """
        target_group = None

        if stage == "main":
            target_group = self.tournament.group_stage
        elif stage == "consolation":
            branch = self.tournament.branches.get("consolation")
            if hasattr(branch, "groups"):
                target_group = branch

        if not target_group:
            return None

        result = {}
        for group_name in target_group.groups.keys():
            # 1. Zpracování hráčů a jejich statistik
            web_players = []
            for p in target_group.rank_players(group_name):
                # Je to jen textový zástupce (placeholder)?
                if isinstance(p, str):
                    web_players.append({
                        "name": p, "games_win": 0, "games_lost": 0,
                        "balls_diff": 0, "points": 0, "is_placeholder": True
                    })
                # Je to reálný hráč?
                else:
                    # Podle toho, zda jsme v hlavní skupině nebo v útěše, sáhneme pro správné statistiky
                    stage_stats_name = "Group" if stage == "main" else "consolation"
                    s = p.stats.get(stage_stats_name, {})
                    diff = p.difference_of_score(stage_stats_name)

                    web_players.append({
                        "name": p.name,
                        "games_win": s.get('games_win', 0),
                        "games_lost": s.get('games_lost', 0),
                        "balls_diff": diff['Balls'],
                        "points": s.get('points', 0),
                        "is_placeholder": False
                    })

            # 2. Zpracování zápasů
            web_matches = []
            for match in target_group.group_matches.get(group_name, []):
                web_matches.append({
                    "match_id": match.match_id,
                    "is_finished": match.is_finished,
                    "is_in_progress": match.is_in_progress,
                    "match_format": match.match_format,
                    "player_a_name": match.player_A.name if not isinstance(match.player_A, str) else match.player_A,
                    "player_b_name": match.player_B.name if not isinstance(match.player_B, str) else match.player_B,
                    "played_sets": match.played_sets,
                    "is_ready": not (isinstance(match.player_A,str) or isinstance(match.player_B,str))
                })

            # Uložíme to celé do slovníku pod názvem skupiny
            result[group_name] = {
                "players": web_players,
                "matches": web_matches
            }

        return result

    def get_playoff_structure_for_web(self, branch_key: str = "main") -> dict | None:
        """
        Vrátí kompletní zformátovanou strukturu pavouka pro web.
        """
        playoff = self.tournament.branches.get(branch_key)
        if not hasattr(playoff, "rounds"):
            return None

        formatted_rounds = {}
        for round_num, matches in playoff.rounds.items():
            formatted_rounds[round_num] = [self._format_match_for_web(m, round_num) for m in matches]

        return formatted_rounds

    def has_active_consolation(self) -> bool:
        """
        Vrací True, pokud větev útěchy existuje a reálně obsahuje data/hráče.
        Určeno primárně pro web (skrývání/zobrazování záložek).
        """
        consolation = self.tournament.branches.get("consolation")
        if not consolation:
            return False

        # Duck typing: Pokud to má "groups" (je to minitabulka)
        if hasattr(consolation, "groups"):
            # any() vrátí True, pokud alespoň jedna skupina není prázdná
            return any(bool(players) for players in consolation.groups.values())

        # Duck typing: Pokud to má "rounds" (je to Playoff pavouk)
        if hasattr(consolation, "rounds"):
            return bool(consolation.rounds)

        return False

    def get_consolation_type(self) -> str | None:
        """
        Vrátí typ aktivní útěchy jako textový řetězec ("minigroup" nebo "playoff").
        Pomáhá šablonám vyhnout se dotazování na jména Python tříd.
        """
        consolation = self.tournament.branches.get("consolation")
        if not consolation:
            return None

        if hasattr(consolation,"groups"):
            return "minigroup"
        if hasattr(consolation,"rounds"):
            return "playoff"

        return None


    def get_final_ranking(self) -> list[dict]:
        """
        Získá konečné pořadí turnaje přes result managera.
        Zajišťuje, že main.py nemusí mluvit přímo s objektem Tournament.
        """
        return self.tournament.results_manager.compute_final_ranking(self.tournament.branches)

    # ===============================
    # DISPEČER
    # ===============================

    def _find_match_and_context(self,match_id: int):
        """
        Najde zápas podle ID napříč celým turnajem.
        Vrací tuple: (nalezený zápas, objekt_fáze_ve_které_se_nachází)
        """
        # 1. hledání ve základních skupinách
        if hasattr(self.tournament, "group_stage") and self.tournament.group_stage:
            for matches in self.tournament.group_stage.group_matches.values():
                for match in matches:
                    if getattr(match, "match_id", None) == match_id:
                        return match, self.tournament.group_stage

        # 2. hledání ve všech dalších větvích (hlavní playoff, útěcha)
        for branch_name, branch in self.tournament.branches.items():
            if not branch:
                continue

            # Pokud je to Playoff pavouk (obsahuje rounds a placement_rounds)
            if hasattr(branch, "rounds"):
                for matches in branch.rounds.values():
                    for match in matches:
                        if getattr(match,"match_id", None) == match_id:
                            return match, branch

                if hasattr(branch, "placement_rounds") and branch.placement_rounds:
                    for bracket_data in branch.placement_rounds.values():
                        for match in bracket_data.get("matches",[]):
                            if getattr(match,"match_id", None) == match_id:
                                return match, branch

            # Pokud je to skupinová fáze (minitabulka)
            elif hasattr(branch,"group_matches"):
                for matches in branch.group_matches.values():
                    for match in matches:
                       if getattr(match, "match_id") == match_id:
                           return match, branch

        return None, None

    def process_match_action(self, match_id: int, action: str, games_a: list = None, games_b: list = None):
        """
        Kompletně zpracuje akci nad zápasem z webu.
        Najde zápas, přepne stav nebo zapíše výsledek a vyvolá kontrolu postupu.
        """
        match, branch_context = self._find_match_and_context(match_id=match_id)

        if not match:
            return

        # Zpracování přepnutí stavu rozkliknutí:
        if action == "toggle_progress":
            match.toggle_in_progress()

        # Zpracování odeslaného výsledku
        elif action == "submit_result" and games_a is not None and games_b is not None:
            played_games = []
            for a,b in zip(games_a, games_b):
                if a == "" and b =="":
                    continue

                if a =="":
                    a = 0
                if b == "":
                    b = 0

                played_games.append((int(a), int(b)))

            match.evaluate_match(played_sets=played_games)


            # Automaticky zavoláme správnou kontrolu postupu podle toho, kde se zápas nachází:
            if hasattr(branch_context, "check_and_proceed"):
                # PLayoff
                branch_context.check_and_proceed(tournament=self.tournament)
            else:
                self.tournament.check_stage_progression()

    def _format_match_for_web(self, match, round_num: int = None) -> dict:
        """Převede jakýkoliv stav zápasu (Match, slot, BYE) do hloupého slovníku pro web."""
        def format_player(p, is_b=False):
            if p is None:
                name = "BYE" if is_b and round_num == 1 else "Čeká se.."
                return {"name": name, "rank": ""}
            if hasattr(p, "name"):
                rank = f"({p.group_rank}{p.group_name})" if getattr(p, "group_rank", None) else ""
                return {"name": p.name, "rank": rank}
            return {"name": str(p), "rank": ""}

        # Je to jen čekající slot (tuple)
        if isinstance(match, tuple):
            return {
                "type": "slot",
                "player_A": format_player(match[0]),
                "player_B": format_player(match[1], is_b=True)
            }

        # Je to reálný zápas
        return {
            "type": "match",
            "match_id": match.match_id,
            "is_finished": match.is_finished,
            "is_in_progress": match.is_in_progress,
            "match_format": match.match_format,
            "player_A": format_player(match.player_A),
            "player_B": format_player(match.player_B, is_b=True),
            "winner_name": match.winner.name if match.winner else None
        }

    def get_playoff_data(self, branch_key: str) -> dict | None:
        """Vrátí kompletní data pro vykreslení celého pavouka (včetně umístění)."""
        branch = self.tournament.branches.get(branch_key)
        if not hasattr(branch, "rounds"):
            return None

        data = {
            "winner": branch.winner.name if getattr(branch, "winner", None) else None,
            "rounds": {},
            "placement_rounds": []
        }

        # 1. Hlavní kola
        for r_num, matches in branch.rounds.items():
            data["rounds"][r_num] = [self._format_match_for_web(m, r_num) for m in matches]

        # 2. Kola o umístění
        if hasattr(branch, "placement_rounds") and branch.placement_rounds:
            sorted_placements = sorted(
                branch.placement_rounds.items(),
                key=lambda x: (x[1]["ranks"][1] - x[1]["ranks"][0], x[1]["ranks"][0]),
                reverse=True
            )
            for name, p_data in sorted_placements:
                formatted_matches = [self._format_match_for_web(m) for m in p_data.get("matches", [])]
                data["placement_rounds"].append({"name": name, "matches": formatted_matches})

        return data


