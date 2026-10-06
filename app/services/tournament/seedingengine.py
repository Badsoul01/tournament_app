from functools import lru_cache
from itertools import permutations


class SeedingEngine:
    """
    SeedingEngine v5

    Univerzalni seeding pro libovolny rozsah poradi start_rank..end_rank.

    Priklady:
      1-2 -> hlavni playoff pro 1. a 2. mista
      3-4 -> utecha pro 3. a 4. mista
      5-6 -> dalsi vykonnostni pavouk
      1-4 -> pavouk pro prvni ctyri z kazde skupiny

    Pravidla:
      1) stejna skupina se NESMI potkat v 1. kole,
      2) prvni kolo preferuje nejlepsi rank vs nejhorsi rank,
      3) BYE dostavaji prednostne lepe umisteni hraci daneho rozsahu,
      4) hraci stejne skupiny se maji potkat co nejpozdeji,
      5) start_rank je anchor rank celeho daneho pavouka,
      6) krizove rozdeleni polovin je relativni ke start_rank.

    Zadny HARDCODED_BRACKETS zde neni.
    """

    MAX_GROUPS = 8
    MAX_MAIN_PLAYERS = 16

    # Kolik nejlepsich variant prvniho kola si nechame pro druhe kolo
    # optimalizace. 8 je pro max. 16 hracu dostatecne a rychle.
    PAIRING_CANDIDATES = 256

    # Pevne kotvy podle velikosti pavouka.
    # Konkretni rank se doplni dynamicky podle start_rank.
    FIXED_ANCHOR_GROUPS = {
        4: {
            "A": 0,
            "B": 1,
        },
        8: {
            "A": 0,
            "C": 1,
            "D": 2,
            "B": 3,
        },
        16: {
            "A": 0,
            "C": 3,
            "D": 4,
            "B": 7,
        },
    }

    # Presne poradi prijemcu BYE podle skupiny.
    # Rank se doplni dynamicky podle start_rank.
    BYE_RECIPIENT_GROUPS = {
        1: ("A",),
        2: ("A", "B"),
        3: ("A", "C", "B"),
        4: ("A", "C", "D", "B"),
    }

    def __init__(self, debug: bool = False):
        self.debug = debug

    # ============================================================
    # 1. VEREJNE API
    # ============================================================

    def build_first_round(
        self,
        groups: dict,
        start_rank: int = 1,
        end_rank: int = 1,
    ) -> list:
        if not groups:
            return []

        if start_rank < 1:
            raise ValueError("start_rank musi byt >= 1.")

        if end_rank < start_rank:
            raise ValueError("end_rank musi byt >= start_rank.")

        players = self._prepare_players(
            groups,
            start_rank,
            end_rank,
        )

        if not players:
            return []

        if len(groups) < 2:
            raise ValueError(
                "Pro pavouk jsou potreba alespon 2 skupiny."
            )

        if len(groups) > self.MAX_GROUPS:
            raise ValueError(
                f"SeedingEngine podporuje maximalne "
                f"{self.MAX_GROUPS} skupin."
            )

        if len(players) > self.MAX_MAIN_PLAYERS:
            raise ValueError(
                f"SeedingEngine podporuje maximalne "
                f"{self.MAX_MAIN_PLAYERS} hracu, "
                f"ale bylo zadano {len(players)}."
            )

        bracket_size = self._next_power_of_two(
            max(2, len(players))
        )

        nodes = self._add_byes(
            players,
            bracket_size,
        )

        bye_count = bracket_size - len(players)
        fixed_bye_recipients = self._get_fixed_bye_recipients(
            players=players,
            bracket_size=bracket_size,
            bye_count=bye_count,
            anchor_rank=start_rank,
        )

        pairing_candidates = self._get_best_pairings(
            nodes=nodes,
            min_rank=start_rank,
            max_rank=end_rank,
            limit=self.PAIRING_CANDIDATES,
            fixed_bye_recipients=fixed_bye_recipients,
        )

        if not pairing_candidates:
            raise ValueError(
                "Nepodarilo se sestavit prvni kolo bez kolize skupin."
            )

        best_result = None

        for pairing_cost, pair_indices in pairing_candidates:
            arrangement_score, arranged_pairs = (
                self._find_best_match_arrangement(
                    nodes=nodes,
                    pairs=pair_indices,
                    bracket_size=bracket_size,
                    anchor_rank=start_rank,
                )
            )

            # Priorita:
            # 1) stejna skupina co nejpozdeji,
            # 2) krizove rozdeleni polovin uvnitr skupiny,
            #    napr. 1A nahore -> 2A dole,
            # 3) prvni vs posledni + spravne BYE,
            # 4) rozprostreni anchor ranku.
            total_score = (
                arrangement_score[0],
                arrangement_score[1],
                pairing_cost,
                arrangement_score[2],
                arrangement_score[3],
            )

            candidate = (
                total_score,
                arranged_pairs,
            )

            if (
                best_result is None
                or candidate[0] < best_result[0]
            ):
                best_result = candidate

        matches = self._pairs_to_matches(
            nodes,
            best_result[1],
        )

        self._debug(
            f"PAVOUK RANK {start_rank}-{end_rank}",
            matches,
        )
        return matches

    # ============================================================
    # 2. KROK A - TVORBA DVOJIC PRO PRVNI KOLO
    # ============================================================

    def _get_best_pairings(
        self,
        nodes: list,
        min_rank: int,
        max_rank: int,
        limit: int,
        fixed_bye_recipients=None,
    ) -> list:
        """
        Najde nekolik nejlepsich kompletnich sparovani.

        Hard pravidla:
          - stejna skupina proti sobe = zakazano,
          - BYE proti BYE = zakazano,
          - u 16clenneho pavouka s 1-4 BYE muze BYE dostat
            pouze predem urceny anchor (1A/1B/1C/1D).

        Soft pravidla:
          - prvni vs posledni.
        """
        count = len(nodes)

        @lru_cache(maxsize=None)
        def solve(mask: int):
            if mask == 0:
                return ((0, ()),)

            first_bit = mask & -mask
            i = first_bit.bit_length() - 1
            remaining = mask & ~first_bit

            candidates = []
            remaining_copy = remaining

            while remaining_copy:
                bit = remaining_copy & -remaining_copy
                j = bit.bit_length() - 1
                remaining_copy &= ~bit

                pair_cost = self._first_round_pair_cost(
                    nodes[i],
                    nodes[j],
                    min_rank,
                    max_rank,
                    fixed_bye_recipients,
                )

                if pair_cost is None:
                    continue

                rest_mask = remaining & ~(1 << j)

                for rest_cost, rest_pairs in solve(rest_mask):
                    candidates.append(
                        (
                            pair_cost + rest_cost,
                            ((i, j),) + rest_pairs,
                        )
                    )

            candidates.sort(
                key=lambda item: (
                    item[0],
                    item[1],
                )
            )

            return tuple(candidates[:limit])

        full_mask = (1 << count) - 1
        return list(solve(full_mask))

    def _first_round_pair_cost(
        self,
        a: dict,
        b: dict,
        min_rank: int,
        max_rank: int,
        fixed_bye_recipients=None,
    ):
        a_bye = a["bye"]
        b_bye = b["bye"]

        # Dve BYE proti sobe nechceme.
        if a_bye and b_bye:
            return None

        if a_bye or b_bye:
            player = b if a_bye else a

            # Pokud mame aktivni pevne BYE kotvy, nikdo jiny BYE dostat nesmi.
            if (
                fixed_bye_recipients is not None
                and player["name"] not in fixed_bye_recipients
            ):
                return None

            # Kdyz pevne kotvy aktivni nejsou, zustava puvodni preference:
            # BYE dostavaji lepe umisteni.
            if fixed_bye_recipients is None:
                return (
                    player["rank"] - min_rank
                ) * 100

            return 0

        # Stejna skupina v 1. kole je absolutne zakazana.
        if a["group"] == b["group"]:
            return None

        # "Prvni s poslednim".
        target_sum = min_rank + max_rank
        rank_sum_error = abs(
            (a["rank"] + b["rank"]) - target_sum
        )

        # Pri stejnem souctu lehce preferujeme vetsi rozdil poradi.
        spread = abs(a["rank"] - b["rank"])
        max_spread = max_rank - min_rank
        spread_penalty = max_spread - spread

        return (
            rank_sum_error * 20
            + spread_penalty
        )

    # ============================================================
    # 3. KROK B - ROZMISTENI ZAPASU V PAVOUKU
    # ============================================================

    def _find_best_match_arrangement(
        self,
        nodes: list,
        pairs: tuple,
        bracket_size: int,
        anchor_rank: int,
    ):
        """
        Rozmisti hotove dvojice do pavouka.

        Pevne kotvy se odvodi podle velikosti pavouka a anchor_ranku.

        Napr. pro anchor_rank == 3 a bracket_size == 8:
          index 0 -> zapas obsahujici 3A
          index 1 -> zapas obsahujici 3C
          index 2 -> zapas obsahujici 3D
          index 3 -> zapas obsahujici 3B

        Ostatni zapasy se optimalizuji kolem techto kotev.
        """
        if not pairs:
            return ((), 0, (), ()), ()

        match_count = len(pairs)
        arranged_base = [None] * match_count

        fixed_positions = self._get_fixed_anchor_positions(
            nodes=nodes,
            pairs=pairs,
            bracket_size=bracket_size,
            anchor_rank=anchor_rank,
        )

        used_pairs = set()

        for position, pair_index in fixed_positions.items():
            if position >= match_count:
                continue

            # Jeden realny zapas muze obsahovat vice anchor hracu
            # (typicky pavouk tvoreny pouze jednim rankem, napr.
            # 3A/3B/3C/3D). V takovem pripade nelze oba hrace
            # zaroven ukotvit na ruzne pozice.
            #
            # Prvni kotvu zachovame a dalsi kolizni kotvu preskocime.
            # Zbytek rozmisteni pak vyresi optimalizace.
            if pair_index in used_pairs:
                continue

            arranged_base[position] = pairs[pair_index]
            used_pairs.add(pair_index)

        remaining_pairs = tuple(
            pair
            for index, pair in enumerate(pairs)
            if index not in used_pairs
        )

        free_positions = [
            index
            for index, pair in enumerate(arranged_base)
            if pair is None
        ]

        best = None

        for perm in permutations(remaining_pairs):
            arranged = list(arranged_base)

            for position, pair in zip(free_positions, perm):
                arranged[position] = pair

            arranged = tuple(arranged)

            score = self._arrangement_score(
                nodes,
                arranged,
                bracket_size,
                anchor_rank,
            )

            candidate = (
                score,
                arranged,
            )

            if (
                best is None
                or candidate[0] < best[0]
                or (
                    candidate[0] == best[0]
                    and candidate[1] < best[1]
                )
            ):
                best = candidate

        return best

    def _arrangement_score(
        self,
        nodes: list,
        arranged_pairs: tuple,
        bracket_size: int,
        anchor_rank: int,
    ) -> tuple:
        """
        Vraci:
          0) pocty predcasnych setkani stejne skupiny po kolech,
          1) pocet poruseni krizove parity polovin,
          2) pocty predcasnych setkani vitezu skupin,
          3) deterministicky tie-break.
        """
        group_positions = {}
        rank_positions = {}

        for match_index, pair in enumerate(arranged_pairs):
            for node_index in pair:
                player = nodes[node_index]

                if player["bye"]:
                    continue

                group_positions.setdefault(
                    player["group"],
                    [],
                ).append(
                    (
                        match_index,
                        player["rank"],
                    )
                )

                rank_positions.setdefault(
                    player["rank"],
                    [],
                ).append(match_index)

        group_round_counts = (
            self._early_meeting_counts(
                group_positions,
                bracket_size,
            )
        )

        parity_penalty = (
            self._group_half_parity_penalty(
                group_positions,
                bracket_size,
                anchor_rank,
            )
        )

        anchor_round_counts = (
            self._winner_meeting_counts(
                rank_positions.get(anchor_rank, []),
                bracket_size,
            )
        )

        deterministic_key = tuple(
            tuple(pair)
            for pair in arranged_pairs
        )

        return (
            group_round_counts,
            parity_penalty,
            anchor_round_counts,
            deterministic_key,
        )

    def _early_meeting_counts(
        self,
        group_positions: dict,
        bracket_size: int,
    ) -> tuple:
        """
        Pocita, kolik dvojic stejne skupiny se muze potkat
        ve 2., 3., ... kole.

        Posledni kolo (finale) netrestame.
        """
        total_rounds = (
            bracket_size.bit_length() - 1
        )

        counts = {
            round_no: 0
            for round_no in range(
                2,
                total_rounds,
            )
        }

        for members in group_positions.values():
            for i in range(len(members)):
                for j in range(
                    i + 1,
                    len(members),
                ):
                    match_a = members[i][0]
                    match_b = members[j][0]

                    round_no = (
                        self._meeting_round_for_matches(
                            match_a,
                            match_b,
                        )
                    )

                    if round_no in counts:
                        counts[round_no] += 1

        return tuple(
            counts[r]
            for r in sorted(counts)
        )

    def _group_half_parity_penalty(
        self,
        group_positions: dict,
        bracket_size: int,
        anchor_rank: int,
    ) -> int:
        """
        Parita je relativni ke skupine.

        Priklad:
          kdyz 1H skonci dole,
          2H ma byt idealne nahore,
          3H dole,
          4H nahore.
        """
        match_count = bracket_size // 2
        half = match_count // 2

        if half == 0:
            return 0

        penalty = 0

        for members in group_positions.values():
            anchor_match = next(
                (
                    match_index
                    for match_index, rank in members
                    if rank == anchor_rank
                ),
                None,
            )

            if anchor_match is None:
                continue

            base_half = (
                0
                if anchor_match < half
                else 1
            )

            for match_index, rank in members:
                if rank == anchor_rank:
                    continue

                actual_half = (
                    0
                    if match_index < half
                    else 1
                )

                # Parita je relativni ke start_rank:
                # start_rank, start_rank+2, ... ve stejne polovine;
                # start_rank+1, start_rank+3, ... v opacne.
                relative_rank = rank - anchor_rank
                expected_half = (
                    base_half
                    if relative_rank % 2 == 0
                    else 1 - base_half
                )

                if actual_half != expected_half:
                    penalty += 1

        return penalty

    def _winner_meeting_counts(
        self,
        winner_positions: list,
        bracket_size: int,
    ) -> tuple:
        """
        Pomocny tie-break:
        hraci s anchor rankem se take snazi byt rozprostreni.
        """
        total_rounds = (
            bracket_size.bit_length() - 1
        )

        counts = {
            round_no: 0
            for round_no in range(
                2,
                total_rounds,
            )
        }

        for i in range(len(winner_positions)):
            for j in range(
                i + 1,
                len(winner_positions),
            ):
                round_no = (
                    self._meeting_round_for_matches(
                        winner_positions[i],
                        winner_positions[j],
                    )
                )

                if round_no in counts:
                    counts[round_no] += 1

        return tuple(
            counts[r]
            for r in sorted(counts)
        )

    def _meeting_round_for_matches(
        self,
        match_a: int,
        match_b: int,
    ) -> int:
        """
        Dva ruzne zapasy prvniho kola:
          sousedni zapasy -> jejich vitezove se mohou potkat ve 2. kole,
          dalsi vetev     -> ve 3. kole,
          atd.
        """
        if match_a == match_b:
            return 1

        return (
            (match_a ^ match_b).bit_length()
            + 1
        )

    # ============================================================
    # 4. PREVOD / PRIPRAVA DAT
    # ============================================================

    def _prepare_players(
        self,
        groups: dict,
        start_rank: int,
        end_rank: int,
    ) -> list:
        players = []

        for group_name in sorted(groups.keys()):
            group_players = groups[group_name]

            for rank in range(
                start_rank,
                end_rank + 1,
            ):
                if rank - 1 < len(group_players):
                    players.append(
                        {
                            "name": f"{rank}{group_name}",
                            "group": group_name,
                            "rank": rank,
                            "bye": False,
                        }
                    )

        # Stabilni poradi.
        players.sort(
            key=lambda p: (
                p["rank"],
                p["group"],
            )
        )

        return players

    def _add_byes(
        self,
        players: list,
        bracket_size: int,
    ) -> list:
        result = [
            player.copy()
            for player in players
        ]

        bye_count = (
            bracket_size - len(result)
        )

        for index in range(bye_count):
            result.append(
                {
                    "name": f"__BYE_{index + 1}",
                    "group": None,
                    "rank": None,
                    "bye": True,
                }
            )

        return result

    def _get_fixed_bye_recipients(
        self,
        players: list,
        bracket_size: int,
        bye_count: int,
        anchor_rank: int,
    ):
        """
        Pro 1-4 BYE vrati presny seznam hracu s nejlepsim rankem
        daneho pavouka.

        Priklady:
          start_rank=1 -> 1A, 1B, 1C, 1D
          start_rank=3 -> 3A, 3B, 3C, 3D
          start_rank=5 -> 5A, 5B, 5C, 5D

        Pokud potrebne skupiny v datech nejsou, vrati None a pouzije se
        obecna preference lepe umistenych hracu.
        """
        if bye_count <= 0:
            return None

        recipient_groups = self.BYE_RECIPIENT_GROUPS.get(bye_count)
        if not recipient_groups:
            return None

        recipients = tuple(
            f"{anchor_rank}{group_name}"
            for group_name in recipient_groups
        )

        existing_names = {
            player["name"]
            for player in players
        }

        if not all(name in existing_names for name in recipients):
            return None

        return frozenset(recipients)

    def _get_fixed_anchor_positions(
        self,
        nodes: list,
        pairs: tuple,
        bracket_size: int,
        anchor_rank: int,
    ) -> dict:
        """
        Vrati mapu index_zapasu -> index_dvojice.

        Kotvy jsou obecne podle anchor_ranku.
        Pro 8clenny pavouk: A nahore, B dole, C/D mezi nimi.
        Pro 16clenny pavouk zustava puvodni A/C/D/B rozlozeni.
        """
        anchor_map = self.FIXED_ANCHOR_GROUPS.get(bracket_size)

        if anchor_map:
            result = {}

            # A a B jsou hlavni okrajove kotvy.
            # C a D jsou az sekundarni.
            # Kdyz jeden zapas obsahuje dva anchor hrace
            # (napr. 3B vs 3C), chceme zachovat B dole,
            # misto aby ho C vytlacilo z okrajove pozice.
            anchor_priority = ("A", "B", "C", "D")

            for group_name in anchor_priority:
                if group_name not in anchor_map:
                    continue

                match_index = anchor_map[group_name]
                player_name = f"{anchor_rank}{group_name}"

                pair_index = self._find_pair_containing_player(
                    nodes,
                    pairs,
                    player_name,
                )

                if pair_index is not None:
                    result[match_index] = pair_index

            if result:
                return result

        return {
            0: self._find_anchor_pair_index(
                nodes,
                pairs,
                anchor_rank,
            )
        }

    def _find_pair_containing_player(
        self,
        nodes: list,
        pairs: tuple,
        player_name: str,
    ):
        for pair_index, pair in enumerate(pairs):
            for node_index in pair:
                if nodes[node_index]["name"] == player_name:
                    return pair_index

        return None

    def _find_anchor_pair_index(
        self,
        nodes: list,
        pairs: tuple,
        anchor_rank: int,
    ) -> int:
        """
        Ukotvi nahore anchor_rank + skupinu A.
        Kdyby A nebyla, vezme abecedne prvni dostupnou skupinu
        s anchor_rankem.
        """
        anchors = [
            p
            for p in nodes
            if not p["bye"] and p["rank"] == anchor_rank
        ]

        if not anchors:
            return 0

        preferred_name = f"{anchor_rank}A"
        names = {p["name"] for p in anchors}
        anchor_name = (
            preferred_name
            if preferred_name in names
            else min(names)
        )

        for pair_index, pair in enumerate(pairs):
            for node_index in pair:
                if nodes[node_index]["name"] == anchor_name:
                    return pair_index

        return 0

    def _pairs_to_matches(
        self,
        nodes: list,
        arranged_pairs: tuple,
    ) -> list:
        matches = []

        for pair in arranged_pairs:
            members = [
                nodes[index]
                for index in pair
            ]

            # BYE vzdy jako druhy slot.
            # U dvou hracu dame lepe umisteneho jako prvniho.
            members.sort(
                key=lambda p: (
                    p["bye"],
                    (
                        p["rank"]
                        if p["rank"] is not None
                        else 999
                    ),
                    p["name"],
                )
            )

            p1 = (
                None
                if members[0]["bye"]
                else members[0]["name"]
            )

            p2 = (
                None
                if members[1]["bye"]
                else members[1]["name"]
            )

            matches.append(
                (p1, p2)
            )

        return matches

    def _prepare_simple_pots(
        self,
        groups: dict,
        start_rank: int,
        end_rank: int,
    ) -> dict:
        pots = {}

        for group_name in sorted(groups.keys()):
            group_players = groups[group_name]

            for rank in range(
                start_rank,
                end_rank + 1,
            ):
                if rank - 1 < len(group_players):
                    pots.setdefault(
                        rank,
                        [],
                    ).append(
                        f"{rank}{group_name}"
                    )

        return pots

    # ============================================================
    # 5. LEGACY ATP GENERATOR (ponechan jako pomocny/fallback)
    # ============================================================

    def _generate_atp_bracket(
        self,
        players: list,
    ) -> list:
        if not players:
            return []

        byes_needed = (
            self._calculating_byes(
                len(players)
            )
        )

        bracket_size = (
            len(players)
            + byes_needed
        )

        all_slots = (
            list(players)
            + [None] * byes_needed
        )

        indices = (
            self._get_seeding_indices(
                bracket_size
            )
        )

        return [
            (
                all_slots[indices[i]],
                all_slots[indices[i + 1]],
            )
            for i in range(
                0,
                len(indices),
                2,
            )
        ]

    def _get_seeding_indices(
        self,
        size: int,
    ) -> list:
        if size <= 1:
            return [0]

        brackets = [0]

        while len(brackets) < size:
            next_brackets = []

            for i, idx in enumerate(brackets):
                pair = (
                    idx,
                    2 * len(brackets) - 1 - idx,
                )

                if i % 2 == 1:
                    pair = (
                        pair[1],
                        pair[0],
                    )

                next_brackets.extend(pair)

            brackets = next_brackets

        return brackets

    def _calculating_byes(
        self,
        total_slots: int,
    ) -> int:
        bracket_size = (
            self._next_power_of_two(
                max(2, total_slots)
            )
        )

        return (
            bracket_size
            - total_slots
        )

    def _next_power_of_two(
        self,
        value: int,
    ) -> int:
        size = 1

        while size < value:
            size *= 2

        return size

    # ============================================================
    # 6. VALIDACE / DIAGNOSTIKA
    # ============================================================

    def validate_first_round(
        self,
        matches: list,
    ) -> dict:
        problems = []

        for index, match in enumerate(matches):
            p1, p2 = match

            if p1 is None or p2 is None:
                continue

            g1 = self._parse_group(p1)
            g2 = self._parse_group(p2)

            if g1 == g2:
                problems.append(
                    f"Zapas {index + 1}: "
                    f"stejna skupina "
                    f"({p1} vs {p2})."
                )

        return {
            "valid": not problems,
            "problems": problems,
        }

    def analyze_bracket(
        self,
        matches: list,
    ) -> dict:
        """
        Jednoducha diagnostika pro testovani v aplikaci.
        """
        validation = (
            self.validate_first_round(matches)
        )

        byes = []

        for p1, p2 in matches:
            if p1 is None and p2 is not None:
                byes.append(p2)
            elif p2 is None and p1 is not None:
                byes.append(p1)

        return {
            "valid_first_round": validation["valid"],
            "problems": validation["problems"],
            "byes": byes,
            "matches": matches,
        }

    def _parse_group(
        self,
        player_name: str,
    ) -> str:
        index = 0

        while (
            index < len(player_name)
            and player_name[index].isdigit()
        ):
            index += 1

        return player_name[index:]

    def _debug(
        self,
        label: str,
        value,
    ) -> None:
        if self.debug:
            print(
                f"DEBUG [{label}]: {value}"
            )
