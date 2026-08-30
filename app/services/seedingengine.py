class SeedingEngine:
    """
    Modulární a přehledný engine pro generování turnajových pavouků
    se zachováním původních kotev, chytrého lineárního řazení a přesných BYE pozic.
    """

    # ==========================================
    # 1. VEŘEJNÉ API
    # ==========================================

    def build_first_round(self, groups: dict, start_rank: int = 0, end_rank: int = 0) -> list:
        """
        Hlavní vstupní bod. Vygeneruje základní pavouk prvního kola
        a následně provede korekci skupinových kolizí[cite: 2].
        """
        matches = self._generate_grouped_bracket(groups, start_rank, end_rank)
        print(f"DEBUG: matches v _build_first_round: {matches}")
        return self._fix_group_collisions(matches)

    # ==========================================
    # 2. GENERÁTORY PAVOUKŮ (ATP / GROUPED)
    # ==========================================

    def _generate_grouped_bracket(self, groups: dict, start_rank: int, end_rank: int) -> list:
        """Rozhoduje mezi klasickým ATP pavoukem (pro útěchu) a chytrým lineárním generátorem[cite: 2]."""
        if start_rank > 1:
            pots = self._prepare_simple_pots(groups, start_rank, end_rank)
            all_players = [p for pot in pots.values() for p in pot]
            print(f"DEBUG: Generuji útěchu pro start_rank ={start_rank} přes ATP.")
            return self._generate_atp_bracket(all_players)

        print(f"DEBUG: Použit chytrý lineární algoritmus s hlídáním sousedních větví.")
        return self._generate_smart_grouped_bracket(groups, start_rank, end_rank)

    def _generate_smart_grouped_bracket(self, groups: dict, start_rank: int, end_rank: int) -> list:
        """Sestavuje chytrý pavouk pro základní postupové skupiny[cite: 2]."""
        pots = self._prepare_pots(groups, start_rank, end_rank)
        if not pots:
            return []

        total_slot_count = sum(len(pot) for pot in pots.values())
        bracket_size, byes_count = self._get_smart_bracket_config(total_slot_count)
        total_matches = bracket_size // 2
        byes_indices = self._get_byes_indices(total_matches, byes_count)

        top_rank = min(pots.keys()) if pots else start_rank
        worst_rank = max(pots.keys()) if pots else start_rank

        # Umístění hlavních kotev (A, B, C, D) a volných losů (BYE)
        final_matches = self._assign_anchors_and_byes(
            total_matches=total_matches,
            byes_indices=byes_indices,
            top_pot=pots.get(top_rank, []).copy(),
            worst_pool=pots.get(worst_rank, []).copy()
        )

        return self._pair_remaining_slots(
            final_matches=final_matches,
            pots=pots,
            top_rank=top_rank,
            end_rank=end_rank
        )

    def _generate_atp_bracket(self, players: list) -> list:
        """Vygeneruje klasický pavouk na základě standardního seedingového algoritmu[cite: 2]."""
        if not players:
            return []

        byes_needed = self._calculating_byes(len(players))
        bracket_size = len(players) + byes_needed
        all_slots = list(players) + [None] * byes_needed

        indices = self._get_seeding_indices(bracket_size)
        return [
            (all_slots[indices[i]], all_slots[indices[i + 1]])
            for i in range(0, len(indices), 2)
        ]

    # ==========================================
    # 3. POMOCNÉ VÝPOČTY A KOTVY
    # ==========================================

    def _prepare_pots(self, groups: dict, start_rank: int, end_rank: int) -> dict:
        """Připraví strukturované slovníkové koše hráčů podle umístění[cite: 2]."""
        pots = {}
        for group_name in sorted(groups.keys()):
            players = groups[group_name]
            for rank_idx in range(start_rank, end_rank + 1):
                if rank_idx - 1 < len(players):
                    slot_info = {"name": f"{rank_idx}{group_name}", "group": group_name, "rank": rank_idx}
                    pots.setdefault(rank_idx, []).append(slot_info)
        return pots

    def _prepare_simple_pots(self, groups: dict, start_rank: int, end_rank: int) -> dict:
        """Připraví jednoduché stringové koše pro ATP pavouka."""
        pots = {}
        for group_name in sorted(groups.keys()):
            players = groups[group_name]
            for rank_idx in range(start_rank, end_rank + 1):
                if rank_idx - 1 < len(players):
                    pots.setdefault(rank_idx, []).append(f"{rank_idx}{group_name}")
        return pots

    def _get_byes_indices(self, total_matches: int, bye_count: int) -> list[int]:
        """Vrátí přesné původní indexy pro umístění BYE slotů[cite: 2]."""
        if total_matches == 4:
            if bye_count == 1: return [0]
            if bye_count == 2: return [0, 3]

        elif total_matches == 8:
            if bye_count == 1: return [0]
            if bye_count == 2: return [0, 7]
            if bye_count == 3: return [0, 3, 7]
            if bye_count == 4: return [0, 3, 4, 7]

        return list(range(bye_count))

    def _assign_anchors_and_byes(self, total_matches: int, byes_indices: list, top_pot: list, worst_pool: list) -> list:
        """Původní bezpečná logika pro umístění kotev (A, B, C, D) a BYE pozic[cite: 2]."""
        final_matches = [None] * total_matches
        assigned_slots = {}

        anchor_map = {"A": 0, "B": total_matches - 1}
        if total_matches >= 8:
            anchor_map["C"] = 3
            anchor_map["D"] = 4

        for group_letter, idx in anchor_map.items():
            if idx >= total_matches:
                continue

            slot_info = next((s for s in top_pot if s["group"] == group_letter), None)
            if slot_info:
                top_pot.remove(slot_info)

                if idx in byes_indices:
                    assigned_slots[idx] = (slot_info["name"], None)
                else:
                    p2 = next((w for w in worst_pool if w["group"] != group_letter), None)
                    if not p2 and worst_pool:
                        p2 = worst_pool[0]

                    if p2:
                        worst_pool.remove(p2)
                        assigned_slots[idx] = (slot_info["name"], p2["name"])
                    else:
                        assigned_slots[idx] = (slot_info["name"], None)

        for idx in byes_indices:
            if idx not in assigned_slots and top_pot:
                slot_info = top_pot.pop(0)
                assigned_slots[idx] = (slot_info["name"], None)

        for idx, match in assigned_slots.items():
            final_matches[idx] = match

        return final_matches

    def _pair_remaining_slots(self, final_matches: list, pots: dict, top_rank: int, end_rank: int) -> list:
        """Proloží a spáruje zbývající volné pozice v pavouku[cite: 2]."""
        used_player_names = {
            match[0] for match in final_matches if match and match[0]
        } | {
            match[1] for match in final_matches if match and match[1]
        }

        pot_1 = [s for s in pots.get(1, []) if s["name"] not in used_player_names]
        lower_pool = [
            s for rank in range(end_rank, 1, -1)
            for s in pots.get(rank, [])
            if s["name"] not in used_player_names
        ]

        total_matches = len(final_matches)
        normal_slots = [i for i in range(total_matches) if final_matches[i] is None]

        mid = total_matches // 2
        top_normals = [s for s in normal_slots if s < mid]
        bottom_normals = [s for s in normal_slots if s >= mid]

        interleaved_slots = [val for pair in zip(top_normals, bottom_normals) for val in pair]
        interleaved_slots.extend(top_normals[len(bottom_normals):])
        interleaved_slots.extend(bottom_normals[len(top_normals):])

        for s in interleaved_slots:
            p1, p2 = self._resolve_best_pair(pot_1, lower_pool, final_matches, s)
            if p1 and p2:
                final_matches[s] = (p1["name"], p2["name"])

        return final_matches

    def _resolve_best_pair(self, pot_1: list, lower_pool: list, final_matches: list, current_slot: int):
        """Vyhodnotí nejlepší dostupnou strategii pro obsazení slotu (Pot1+Lower, Lower+Lower, Pot1+Pot1, Emergency)."""
        # 1. Kombinace Pot 1 + Lower Pool
        if pot_1 and lower_pool:
            p1, p2, idx1, idx2 = self._find_valid_pair(pot_1, lower_pool, final_matches, current_slot)
            if p1:
                return pot_1.pop(idx1), lower_pool.pop(idx2)

        # 2. Čistě Lower Pool
        if len(lower_pool) >= 2:
            p1, p2, idx1, idx2 = self._find_valid_pair(lower_pool, lower_pool, final_matches, current_slot)
            if p1:
                for i_rem in sorted([idx1, idx2], reverse=True):
                    lower_pool.pop(i_rem)
                return p1, p2

        # 3. Čistě Pot 1
        if len(pot_1) >= 2:
            p1, p2, idx1, idx2 = self._find_valid_pair(pot_1, pot_1, final_matches, current_slot)
            if p1:
                for i_rem in sorted([idx1, idx2], reverse=True):
                    pot_1.pop(i_rem)
                return p1, p2

        # 4. Nouzové řešení (Emergency)
        emergency = pot_1 + lower_pool
        if len(emergency) >= 2:
            p1, p2 = emergency.pop(0), emergency.pop(0)
            for p in (p1, p2):
                if p in pot_1: pot_1.remove(p)
                elif p in lower_pool: lower_pool.remove(p)
            return p1, p2

        return None, None

    def _find_valid_pair(self, pool1: list, pool2: list, final_matches: list, current_slot: int) -> tuple:
        """Vyhledá platnou dvojici hráčů s ohledem na kolize skupin[cite: 2]."""
        if not pool1 or not pool2:
            return None, None, -1, -1

        partner_slot = current_slot ^ 1
        forbidden_groups = set()
        if partner_slot < len(final_matches) and final_matches[partner_slot] is not None:
            match = final_matches[partner_slot]
            if match[0]: forbidden_groups.add(match[0][-1])
            if match[1]: forbidden_groups.add(match[1][-1])

        best_candidate = None
        best_indices = (-1, -1)

        for i, c1 in enumerate(pool1):
            g1 = c1["group"]
            if g1 in forbidden_groups:
                continue

            start_j = i + 1 if pool1 is pool2 else 0
            for j in range(start_j, len(pool2)):
                c2 = pool2[j]
                g2 = c2["group"]

                if g1 != g2 and g2 not in forbidden_groups:
                    return c1, c2, i, j

                if g1 != g2 and not best_candidate:
                    best_candidate = (c1, c2)
                    best_indices = (i, j)

        if best_candidate:
            return best_candidate[0], best_candidate[1], best_indices[0], best_indices[1]

        for i, c1 in enumerate(pool1):
            g1 = c1["group"]
            start_j = i + 1 if pool1 is pool2 else 0
            for j in range(start_j, len(pool2)):
                c2 = pool2[j]
                if g1 != c2["group"]:
                    return c1, c2, i, j

        return None, None, -1, -1

    # ==========================================
    # 4. POST-PROCESSING KOREKCE KOLIZÍ
    # ==========================================

    def _fix_group_collisions(self, final_matches: list) -> list:
        """Provede dodatečné prohození pro odstranění sousedních a partnerských kolizí skupin[cite: 2]."""
        def get_rank(p_str):
            return int(p_str[0]) if p_str and p_str[0].isdigit() else 0

        def get_group(p_str):
            return p_str[-1] if p_str else ""

        def get_all_forbidden_groups(idx, matches):
            forbidden = set()
            # 1. XOR partner
            partner_idx = idx ^ 1
            if 0 <= partner_idx < len(matches) and matches[partner_idx]:
                m = matches[partner_idx]
                if m[0]: forbidden.add(get_group(m[0]))
                if m[1]: forbidden.add(get_group(m[1]))

            # 2. Lineární sousedé (i-1 a i+1)
            for n_idx in (idx - 1, idx + 1):
                if 0 <= n_idx < len(matches) and matches[n_idx]:
                    m = matches[n_idx]
                    if m[0]: forbidden.add(get_group(m[0]))
                    if m[1]: forbidden.add(get_group(m[1]))

            return forbidden

        def is_bad_match(m, idx, matches):
            if not m or not m[0] or not m[1]:
                return False
            g1, g2 = get_group(m[0]), get_group(m[1])
            r1, r2 = get_rank(m[0]), get_rank(m[1])

            if g1 == g2 or (r1 > 1 and r2 > 1 and r1 == r2):
                return True

            forbidden = get_all_forbidden_groups(idx, matches)
            return g1 in forbidden or g2 in forbidden

        protected_indices = {0, len(final_matches) - 1}

        for _ in range(20):
            changed = False
            for i in range(len(final_matches)):
                if i in protected_indices:
                    continue
                m_i = final_matches[i]
                if not m_i or not m_i[0] or not m_i[1]:
                    continue

                if not is_bad_match(m_i, i, final_matches):
                    continue

                for j in range(len(final_matches)):
                    if i == j or j in protected_indices:
                        continue
                    m_j = final_matches[j]
                    if not m_j or not m_j[0] or not m_j[1]:
                        continue

                    for slot_i in (0, 1):
                        for slot_j in (0, 1):
                            cand_i_players = list(m_i)
                            cand_j_players = list(m_j)

                            cand_i_players[slot_i], cand_j_players[slot_j] = cand_j_players[slot_j], cand_i_players[slot_i]
                            new_i = tuple(cand_i_players)
                            new_j = tuple(cand_j_players)

                            final_matches[i] = new_i
                            final_matches[j] = new_j

                            if not is_bad_match(new_i, i, final_matches) and not is_bad_match(new_j, j, final_matches):
                                changed = True
                                break
                            else:
                                final_matches[i] = m_i
                                final_matches[j] = m_j

                        if changed: break
                    if changed: break
                if changed: break

            if not changed: break

        print(f"DEBUG: matches v _fix_group_collisions: {final_matches}")
        return final_matches

    # ==========================================
    # 5. MATEMATICKÉ UTILITKY
    # ==========================================

    def _get_seeding_indices(self, size: int) -> list[int]:
        if size <= 1:
            return [0]

        brackets = [0]
        while len(brackets) < size:
            next_brackets = []
            for i, idx in enumerate(brackets):
                pair = (idx, 2 * len(brackets) - 1 - idx)
                if i % 2 == 1:
                    pair = (pair[1], pair[0])
                next_brackets.extend(pair)
            brackets = next_brackets
        return brackets

    def _calculating_byes(self, total_slots: int) -> int:
        size_of_bracket = 2
        while size_of_bracket < total_slots:
            size_of_bracket *= 2
        return size_of_bracket - total_slots

    def _get_smart_bracket_config(self, num_players: int):
        if num_players <= 4:
            target_size = 4
        elif num_players <= 8:
            target_size = 8
        elif num_players <= 16:
            target_size = 16
        else:
            target_size = 32

        byes_count = target_size - num_players
        return target_size, byes_count