import itertools
from models import db, Group as GroupModel,Player as PlayerModel, Match as MatchModel, Bracket as BracketModel
from player import PlayerHelper
from playoff import Playoff

class GroupManager:
    """
    Třída zodpovědná za generování a správu zápasů ve skupinách
    přímo nad databázovými modely v PostgreSQL.
    """

    def __init__(self, tournament_id: int, match_format: int):
        self.tournament_id = tournament_id
        self.match_format = match_format

    def generate_group_matches(self) -> None:
        """
        Vygeneruje zápasy pro všechny skupiny daného turnaje spravedlivou
        kruhovou metodou (round-robin) a uloží je do tabulky matches.
        """
        # Načteme všechny hlavní skupiny tohoto turnaje z databáze
        groups = GroupModel.query.filter_by(
            tournament_id=self.tournament_id,
            is_consolation=False
        ).all()

        for group in groups:
            # Získáme seznam hráčů přiřazených k této skupině přes SQLAlchemy relaci
            match_players = list(group.players)

            # Pokud je lichý počet hráčů, přidáme None (volno / BYE)
            if len(match_players) % 2 != 0:
                match_players.append(None)

            n = len(match_players)
            round_count = n - 1
            half = n // 2

            # Kruhová metoda generování kol
            for r in range(round_count):
                for i in range(half):
                    player_a = match_players[i]
                    player_b = match_players[n - 1 - i]

                    # Pokud nejde o volno (BYE), vytvoříme záznam zápasu v DB
                    if player_a is not None and player_b is not None:
                        db_match = MatchModel(
                            match_type="group",
                            match_format=str(self.match_format),
                            tournament_id=self.tournament_id,
                            group_id=group.id,
                            player_a_id=player_a.id,
                            player_b_id=player_b.id,
                            is_finished=False
                        )
                        db.session.add(db_match)

                # Rotace hráčů pro další kolo kruhové metody
                match_players = [match_players[0]] + [match_players[-1]] + match_players[1:-1]

        # Uložíme všechny vygenerované zápasy naráz do databáze jedním příkazem
        db.session.commit()
        print(
            f"DEBUG: Zápasy ve skupinách pro turnaj ID {self.tournament_id} byly úspěšně vygenerovány a uloženy do DB.")

    @staticmethod
    def are_all_matches_played(group_id: int) -> bool:
        """
        Zkontroluje v databázi, zda jsou všechny zápasy v dané skupině dohrané.
        """
        matches = MatchModel.query.filter_by(group_id=group_id).all()
        if not matches:
            return False
        return all(match.is_finished for match in matches)

    def handle_match_completion(self, match_id: int, current_tournament) -> None:
        """Rozhodne o vyhodnocení zápasu podle toho, kam patřil."""
        db_match = MatchModel.query.get(match_id)
        if not db_match:
            return

        if db_match.group_id:
            self._process_standard_group_finish(db_match, current_tournament)
        elif db_match.bracket_id:
            self._process_minigroup_finish(db_match, current_tournament)

    def _process_standard_group_finish(self, db_match, current_tournament) -> None:
        """Privátní metoda: Vyhodnotí zápas ve skupině a případně posune hráče dál."""
        if db_match.player_a_id: PlayerHelper.recalculate_player_stats(db_match.player_a_id, "Group")
        if db_match.player_b_id: PlayerHelper.recalculate_player_stats(db_match.player_b_id, "Group")

        db.session.commit()

        group = GroupModel.query.get(db_match.group_id)
        if not self.are_all_matches_played(group.id):
            return

        group.is_finished = True
        db.session.commit()

        ranked = self.rank_players(group.id, "Group")
        adv_count = current_tournament.advance_per_group
        advancing, eliminated = ranked[:adv_count], ranked[adv_count:]

        letter = group.name.replace("Skupina ", "").strip()
        for idx, p in enumerate(advancing): p.group_seed = f"{idx + 1}{letter}"
        for idx, p in enumerate(eliminated): p.group_seed = f"{idx + 1 + adv_count}{letter}"
        db.session.commit()

        # Posun do Hlavního Playoff
        main_bracket = BracketModel.query.filter_by(tournament_id=self.tournament_id, name="Hlavní Playoff").first()
        if main_bracket:
            engine = Playoff(self.tournament_id, current_tournament.playoff_match_format, "main",
                             current_tournament.playoff_elimination_action, bracket_id=main_bracket.id)
            engine.update_slots_with_players(letter, advancing)
            engine.save_to_db()

        # Posun do Útěchy (Playoff B)
        if eliminated:
            cons_bracket = BracketModel.query.filter_by(tournament_id=self.tournament_id, is_consolation=True).first()
            if cons_bracket and cons_bracket.bracket_type == "elimination":
                main_groups_count = GroupModel.query.filter_by(tournament_id=self.tournament_id,
                                                               is_consolation=False).count()
                cons_engine = Playoff(self.tournament_id, current_tournament.playoff_match_format, "consolation",
                                      current_tournament.playoff_elimination_action,
                                      rank_offset=current_tournament.advance_per_group * main_groups_count,
                                      bracket_id=cons_bracket.id)
                cons_engine.update_slots_with_players(letter, eliminated, start_rank=adv_count)
                cons_engine.save_to_db()

            elif cons_bracket and cons_bracket.bracket_type == "round_robin":
                # 1. Načteme aktuální šablonu minitabulky z JSONu
                tree_data = cons_bracket.tree_data or {}
                matches_list = tree_data.get("matches", [])

                # 2. Projdeme všechny definované dvojice v minitabulce
                for slot_a, slot_b in matches_list:
                    p_a_id = slot_a if isinstance(slot_a, int) else None
                    p_b_id = slot_b if isinstance(slot_b, int) else None

                    # Pokud je slot textový (např. "3A"), zkusíme najít reálné ID hráče podle group_seed
                    if isinstance(slot_a, str):
                        p_obj = PlayerModel.query.filter_by(tournament_id=self.tournament_id, group_seed=slot_a).first()
                        if p_obj:
                            p_a_id = p_obj.id

                    if isinstance(slot_b, str):
                        p_obj = PlayerModel.query.filter_by(tournament_id=self.tournament_id, group_seed=slot_b).first()
                        if p_obj:
                            p_b_id = p_obj.id

                    # 3. Jakmile máme oba hráče reálně dostupné (žádné textové seedy), vytvoříme zápas!
                    if p_a_id is not None and p_b_id is not None:
                        # Zkontrolujeme, jestli už tento vzájemný zápas v minitabulce existuje (obě strany)
                        existing_match = MatchModel.query.filter(
                            MatchModel.bracket_id == cons_bracket.id,
                            ((MatchModel.player_a_id == p_a_id) & (MatchModel.player_b_id == p_b_id)) |
                            ((MatchModel.player_a_id == p_b_id) & (MatchModel.player_b_id == p_a_id))
                        ).first()

                        if not existing_match:
                            db_match = MatchModel(
                                match_type="minigroup",
                                match_format=str(current_tournament.group_match_format),
                                tournament_id=self.tournament_id,
                                bracket_id=cons_bracket.id,
                                player_a_id=p_a_id,
                                player_b_id=p_b_id,
                                is_finished=False
                            )
                            db.session.add(db_match)
                            db.session.commit()

                db.session.commit()

    def _process_minigroup_finish(self, db_match, current_tournament) -> None:
        """Privátní metoda: Vyhodnotí zápas v minitabulce a rozdělí konečná umístění."""
        if db_match.player_a_id: PlayerHelper.recalculate_player_stats(db_match.player_a_id, "minigroup")
        if db_match.player_b_id: PlayerHelper.recalculate_player_stats(db_match.player_b_id, "minigroup")

        cons_bracket = BracketModel.query.get(db_match.bracket_id)
        if not cons_bracket or cons_bracket.bracket_type != "round_robin":
            return

        # 1. Zkontrolujeme, zda už dohrály VŠECHNY základní skupiny v turnaji
        all_groups = GroupModel.query.filter_by(tournament_id=self.tournament_id, is_consolation=False).all()
        if not all(g.is_finished for g in all_groups):
            return  # Pokud základní skupiny ještě neskončily, minitabulku NEVYHODNOCUJEME do konce!

        matches = MatchModel.query.filter_by(bracket_id=cons_bracket.id).all()
        if matches and all(m.is_finished for m in matches):
            player_ids = {m.player_a_id for m in matches if m.player_a_id} | {m.player_b_id for m in matches if m.player_b_id}
            players = PlayerModel.query.filter(PlayerModel.id.in_(player_ids)).all()
            main_groups_count = GroupModel.query.filter_by(tournament_id=self.tournament_id,
                                                           is_consolation=False).count()
            start_rank = (current_tournament.advance_per_group * main_groups_count) + 1
            ranked = sorted(players, key=lambda p: (PlayerHelper.get_or_create_stats(p.id, "minigroup").points,
                                                    PlayerHelper.difference_of_score(p.id, "minigroup")["Balls"]),
                            reverse=True)
            for idx, p in enumerate(ranked):
                PlayerHelper.set_final_rank(p.id, start_rank + idx, stage_name="minigroup")

    def rank_players(self, group_id: int, stage_name: str = "Group") -> list:
        group = GroupModel.query.get(group_id)
        if not group: return []

        if group.is_consolation:
            player_ids = {m.player_a_id for m in group.matches if m.player_a_id} | {m.player_b_id for m in group.matches if m.player_b_id}
            players = PlayerModel.query.filter(PlayerModel.id.in_(player_ids)).all()
        else:
            players = list(group.players)

        matches = MatchModel.query.filter_by(group_id=group_id, is_finished=True).all()
        sorted_players = sorted(players, key=lambda p: PlayerHelper.get_sorting_stats(p.id, stage_name), reverse=True)
        final_ranked = []

        for _, group_iter in itertools.groupby(sorted_players, key=lambda p: PlayerHelper.get_sorting_stats(p.id, stage_name)[:1]):
            subgroup = list(group_iter)
            if len(subgroup) == 1:
                final_ranked.extend(subgroup)
            else:
                final_ranked.extend(self._resolve_mini_group(subgroup, matches))

        return final_ranked

    def _resolve_mini_group(self, subgroup: list, matches: list) -> list:
        sub_ids = {p.id for p in subgroup}
        rel_matches = [m for m in matches if m.player_a_id in sub_ids and m.player_b_id in sub_ids]
        if not rel_matches: return subgroup

        mini_stats = {p.id: {"points": 0, "game_diff": 0, "ball_diff": 0} for p in subgroup}
        for m in rel_matches:
            # Spočítáme celkové skóre setů z nové tabulky match_results
            p_a_sets = 0
            p_b_sets = 0
            if hasattr(m, 'match_results') and m.match_results:
                for s in m.results:
                    if s.score_a > s.score_b:
                        p_a_sets += 1
                    elif s.score_b > s.score_a:
                        p_b_sets += 1

            if p_a_sets > p_b_sets:
                mini_stats[m.player_a_id]["points"] += 3
            elif p_a_sets == p_b_sets:
                mini_stats[m.player_a_id]["points"] += 1
                mini_stats[m.player_b_id]["points"] += 1
            else:
                mini_stats[m.player_b_id]["points"] += 3

        return sorted(subgroup, key=lambda p: (mini_stats[p.id]["points"], PlayerHelper.get_sorting_stats(p.id, "Group")), reverse=True)