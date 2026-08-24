
class SeedingEngine:

    def __init__(self,tournament_format: str):
        self.tournament_format: str = tournament_format

    # ==========================================
    # VEŘEJNÉ API (HLAVNÍ METODY)
    # ==========================================

    def build_first_round(self,groups: dict, players: list = None , start_rank: int = 0,end_rank: int=0) -> list:
        """
        Hlavní metoda, která funguje jako vyhybka.
        Podle formátu turnaje rozhodne, jaký matematický algoritmus se použije.
        """
        if self.tournament_format == "groups_and_playoff":
            print(F"DEBUG: POUŽIT GROUPED METODA {self.tournament_format}")
            return self._generate_grouped_bracket(groups, start_rank=start_rank,end_rank=end_rank)

        elif self.tournament_format == "playoff":
            print(F"DEBUG: POUŽIT ATP METODA {self.tournament_format}")
            return self._generate_atp_bracket(players=players)

        return []


    # ==========================================
    # INTERNÍ POMOCNÉ METODY (PRIVÁTNÍ)
    # ==========================================

    def _generate_atp_bracket(self, players: list) -> list:
        """
        Vygeneruje nasazení pole žebříčku/pořadí v seznamu.
        První hraje s posledním atd.
        """
        if not players:
            return []

        # Zjistíme počet potřebných BYE
        byes_needed = self._calculating_byes(len(players))
        bracket_size = len(players) + byes_needed
        # 2. Doplníme prázná místa (BYE)
        all_slots = list(players)
        for _ in range(byes_needed):
            all_slots.append(None)


        # 3. Získáme matematické pořadí (1-8, 4-5 atd)
        indices = self._get_seeding_indices(bracket_size)

        # 4. Vytvoření zápasů
        paired_slots = []
        for i in range(0, len(indices), 2):
            player_a = all_slots[indices[i]]
            player_b = all_slots[indices[i + 1]]

            paired_slots.append((player_a, player_b))

        return paired_slots

    def _get_seeding_indices(self,size: int) -> list[int]:
        """
        Vrátí pořadí seedů pro standardní vyřazovací pavouk.
        Např. pro 8 hráčů: 1-8,4-5,3-6,2-7
        """
        if size <=1:
            return [0]

        brackets = [0]
        while len(brackets) < size:
            next_brackets = []

            for i, idx in enumerate(brackets):
                pair = (idx, 2 * len(brackets) -1 - idx)

                # Univerzální zrcadlo:

                if i % 2 == 1:
                    pair = (pair[1],pair[0])

                next_brackets.extend(pair)

            brackets = next_brackets
            print(f"DEBUG: počet bracketů: {brackets}")
        return brackets

    def _calculating_byes(self, total_slots: int) -> int:
        """
        Spočítá počet potřebných volných lusů(BYE) bez nutnosti znát hráče.
        """
        size_of_bracket = 2
        while size_of_bracket < total_slots:
            size_of_bracket *= 2
        return size_of_bracket - total_slots

    def _get_smart_bracket_config(self,num_players: int):
        if num_players <= 4:
            target_size = 4
            byes_count = target_size - num_players
        elif num_players <= 8:
            target_size = 8
            byes_count = target_size - num_players
        elif num_players <= 16:
            target_size = 16
            byes_count = target_size -num_players

        return target_size,byes_count


    def _generate_grouped_bracket(self,groups: dict, start_rank: int, end_rank: int) -> list:
        """
        Hlavní metoda pro skupinové turnaje.
        Rozhoduje mezi XOR algoritmem (mocniny dvou skupin) a lineárním algoritmem(zbytek)
        """
        if start_rank > 1:
            pots = {}
            group_names = sorted(groups.keys())
            for group_name in group_names:
                players = groups[group_name]
                for rank_idx in range(start_rank, end_rank +1):
                    if rank_idx - 1 < len(players):
                        pots.setdefault(rank_idx, []).append(f"{rank_idx}{group_name}")
            all_players = [slot for pot in pots.values() for slot in pot]
            print(f"DEBUG: Generuji útěchu pro start_rank ={start_rank} přes ATP.")
            return self._generate_atp_bracket(all_players)

        group_names = sorted(groups.keys())
        num_groups = len(group_names)

        # Kontrola, zda je počet skupin mocninou dvou
        is_power_of_two = num_groups >0 and (num_groups & (num_groups - 1)) == 0
        if is_power_of_two:
            print(f"DEBUG: Použit XOR algoritmus pro {num_groups} skupin.")
            return self._generate_xor_grouped_bracket(groups, start_rank, end_rank)
        else:
            print(f"DEBUG: Použit lineární alogoritmus pro {num_groups} skupin.")
            return self._generate_smart_grouped_bracket(groups,start_rank, end_rank)


    def _generate_xor_grouped_bracket(self,groups:dict, start_rank: int, end_rank: int) -> list:
        """
        XOR algoritmus pro ideální počty skupin (mocniny dvou)
        """
        group_names = sorted(groups.keys())
        num_groups = len(group_names)

        num_bracket = 2
        while num_bracket <num_groups:
            num_bracket *= 2

        # Doplníme chybějící sloty pro neexistující skupiny
        padded_groups = list(group_names)
        while len(padded_groups) < num_bracket:
            padded_groups.append(None)

        # 1. Vytvoříme prázdné koše (čtvrtiny/poloviny) podle počtu skupin
        buckets = [[] for _ in range(num_bracket)]

        # 2. Do každého koše jedno písmenko, rotujeme pro každé pořadí
        for rank in range(start_rank, end_rank + 1):

            #Rozdáme hráče do košů
            for i in range(num_bracket):
                source_index = i ^ ((rank - 1) % num_bracket)
                g = padded_groups[source_index]

                if g is not None and g in groups and len(groups[g]) >= rank:
                    buckets[i].append(f"{rank}{g}")
                else:
                    buckets[i].append(None)

        # Každý koš samostatně domplníme o Bye a necháme ATP, at ho spáruje unvitř
        final_matches = []
        bucket_order = self._get_seeding_indices(num_bracket)

        for target_position, bucket_index in enumerate(bucket_order):
            bucket = buckets[bucket_index]

            # ATP nám spáruje prvního s posledním unvitř čtvrtiny
            bucket_matches = self._generate_atp_bracket(bucket)

            # Pokud jsme ve "spodní části jakékoliv větve (lichý index
            # zápasy otočíme, aby favorit padl na vnější okraj pavouka.
            if target_position % 2 == 1:
                bucket_matches.reverse()

            final_matches.extend(bucket_matches)

        return final_matches

    def _generate_smart_grouped_bracket(self,groups:dict,start_rank:int, end_rank:int) -> list:
        """
        lineární/chytrý algoritmus pro nestandartní počty skupin
        Hlídá fixní BYE indexy a zamezuje kolizím v 2.kole.
        """
        #1. Rozřazení hráčů do "košů" podle umístění ve skupině
        pots = self._prepare_pots(groups=groups,start_rank=start_rank,end_rank= end_rank)
        if not pots:
            return []
        all_advancing = [slot for pot in pots.values() for slot in pot]
        total_slot_count = len(all_advancing)

        # Zjištění velikosti pavouka a počtu BYE
        bracket_size, byes_count = self._get_smart_bracket_config(total_slot_count)
        total_matches = bracket_size // 2

        # 2. Určení přesných indexů pro volné losy (BYE)
        byes_indices = self._get_byes_indices(total_matches,byes_count)

        # 3. Získání nejlepších a nehorších košů pro párování kotev
        top_rank = min(pots.keys()) if pots else start_rank
        worst_rank = max(pots.keys()) if pots else start_rank
        top_pot = pots.get(top_rank, []).copy()
        worst_pool = pots.get(worst_rank,[]).copy()

        # 4. Kotvení favoritů (A,B,C,D) a nasazení BYE
        final_matches = self._assign_anchors_and_byes(
            total_matches=total_matches,
            byes_indices=byes_indices,
            top_pot=top_pot,
            worst_pool= worst_pool
        )

        # 5. Křížové spárování zbytku (zamezí kolizuím ze stejných skupin)
        final_matches = self._pair_remaining_slots(
            final_matches = final_matches,
            pots = pots,
            top_rank=top_rank,
            end_rank=end_rank
        )

        return final_matches

    def _prepare_pots(self,groups:dict, start_rank: int, end_rank:int) -> dict:
        """Vyextrahuje hráče ze skupin a rozdělí je do košů (pots) podle umístění."""
        pots = {}
        for group_name in sorted(groups.keys()):
            players = groups[group_name]
            for rank_idx in range(start_rank,end_rank + 1):
                # Kontrola, zda má skupina dostatek hráčů pro tento rank
                if rank_idx -1 < len(players):
                    slot_info = {"name": f"{rank_idx}{group_name}", "group":group_name, "rank": rank_idx}
                    pots.setdefault(rank_idx,[]).append(slot_info)
        return pots

    def _get_byes_indices(self,total_matches: int, bye_count: int) -> list[int]:
        """Určí, na kterých indexech zápasů budou umísstěny volné losy (BYE) tak, aby byli rovnoměrné."""
        if total_matches == 4:
            if bye_count == 1: return [0]
            if bye_count == 2: return [0,3]

        elif total_matches == 8:
            if bye_count == 1: return [0]
            if bye_count == 2: return [0,7]
            if bye_count == 3: return [0,3,7]
            if bye_count == 4: return [0,3,4,7]

        return list(range(bye_count))

    def _assign_anchors_and_byes(self,total_matches: int, byes_indices: list, top_pot: list, worst_pool: list) -> list:
        """
        Pevně ukotví vítěze skupin na kontrétní místa v pavouku (C, D fixně na střřed)
        Následně k nm přidělí buď BYE, nebo nejslabšího dostupného soupeře.
        """
        final_matches = [None] * total_matches
        assigned_slots = {}

        # Definice kotevních pozic pro jednotlivé skupiny
        anchor_map = {"A": 0, "B": total_matches-1}
        if total_matches>=8:
            anchor_map["C"] = 3
            anchor_map["D"] = 4

        # Nasazení favoritů na kotvy
        for group_letter, idx in anchor_map.items():
            if idx >= total_matches:
                continue

            slot_info = next((s for s in top_pot if s["group"] == group_letter), None)
            if slot_info:
                top_pot.remove(slot_info)

                if idx in byes_indices:
                    # Favorit dosává BYE
                    assigned_slots[idx] = (slot_info["name"], None)
                else:
                    # Spárování s nejhorším dostupným soupeřem z jiné skupiny
                    p2 = next((w for w in worst_pool if w["group"] != group_letter), None)
                    if not p2 and worst_pool:
                        p2 = worst_pool[0]

                    if p2:
                        worst_pool.remove(p2)
                        assigned_slots[idx] = (slot_info["name"], p2["name"])
                    else:
                        assigned_slots[idx] = (slot_info["name"], None)

        # 2. Doplění zbýávajících BYE slotů pro případné další vítěze v top koši
        for idx in byes_indices:
            if idx not in assigned_slots and top_pot:
                slot_info = top_pot.pop(0)
                assigned_slots[idx] = (slot_info["name"], None)

        # 3. Zápis  do výsledného pole zápasů
        for idx, match in assigned_slots.items():
            final_matches[idx] = match

        return final_matches

    def _pair_remaining_slots(self, final_matches: list, pots: dict, top_rank: int, end_rank: int) -> list:
        """
        Doplní volná místa v pavouku. Řeší křížové párování a zamezuje kolizím,
        aby se hráči ze stejné skupiny nepotkali hned ve 2. kole.
        """
        # 1. Evidence už nasazených hráčů (z předchozí kotevní metody)
        used_player_names = set()
        for match in final_matches:
            if match is not None:
                if match[0]: used_player_names.add(match[0])
                if match[1]: used_player_names.add(match[1])

        # 2. Vytvoření bazénů volných hráčů
        active_pot_1 = [s for s in pots.get(top_rank, []) if s["name"] not in used_player_names]
        lower_pool = []
        for rank in range(end_rank, 1, -1):
            for s in pots.get(rank, []):
                if s["name"] not in used_player_names:
                    lower_pool.append(s)

        # 3. Získání a propletení prázdných slotů (interleaving), abychom pavouka plnili rovnoměrně
        total_matches = len(final_matches)
        normal_slots = [i for i in range(total_matches) if final_matches[i] is None]

        mid = total_matches // 2
        top_normals = [s for s in normal_slots if s < mid]
        bottom_normals = [s for s in normal_slots if s >= mid]

        interleaved_slots = []
        for t, b in zip(top_normals, bottom_normals):
            interleaved_slots.append(t)
            interleaved_slots.append(b)

        # Pokud by byla jedna polovina větší (lichý počet volných)
        if len(top_normals) > len(bottom_normals):
            interleaved_slots.extend(top_normals[len(bottom_normals):])
        elif len(bottom_normals) > len(top_normals):
            interleaved_slots.extend(bottom_normals[len(top_normals):])

        # 4. Spárování slotů strategiemi s hlídáním kolizí (XOR logikou ^ 1)
        for s in interleaved_slots:
            partner_slot = s ^ 1
            forbidden_group = None
            if partner_slot < len(final_matches) and final_matches[partner_slot] is not None:
                partner_match = final_matches[partner_slot]
                if partner_match[0] is not None:
                    forbidden_group = partner_match[0][-1]  # Písmeno skupiny soupeře pro další kolo

            p1, p2 = None, None

            # STRATEGIE A: Zbylá první místa vs 2+ místa z nižších košů
            p1, p2, idx1, idx2 = self._find_valid_pair(active_pot_1, lower_pool, forbidden_group)
            if p1:
                active_pot_1.pop(idx1)
                lower_pool.pop(idx2)

            # STRATEGIE B: Pokud došla první místa (párujeme nižší s nižšími - předáme stejný seznam 2x)
            if not p1 and len(lower_pool) >= 2:
                p1, p2, idx1, idx2 = self._find_valid_pair(lower_pool, lower_pool, forbidden_group)
                if p1:
                    # Musíme smazat odzadu, aby se nám nerozhodily indexy
                    for idx_to_rem in sorted([idx1, idx2], reverse=True):
                        lower_pool.pop(idx_to_rem)

            # STRATEGIE C: Zbyly už pouze jedničky navzájem (předáme stejný seznam 2x)
            if not p1 and len(active_pot_1) >= 2:
                p1, p2, idx1, idx2 = self._find_valid_pair(active_pot_1, active_pot_1, forbidden_group)
                if p1:
                    for idx_to_rem in sorted([idx1, idx2], reverse=True):
                        active_pot_1.pop(idx_to_rem)

            # NOUZOVÁ POJISTKA: Ignorujeme pravidla
            if not p1:
                emergency_pool = active_pot_1 + lower_pool
                if len(emergency_pool) >= 2:
                    p1, p2 = emergency_pool.pop(0), emergency_pool.pop(0)
                    # Syncneme odstranění s původními seznamy
                    if p1 in active_pot_1:
                        active_pot_1.remove(p1)
                    else:
                        lower_pool.remove(p1)
                    if p2 in active_pot_1:
                        active_pot_1.remove(p2)
                    else:
                        lower_pool.remove(p2)

            if p1 and p2:
                final_matches[s] = (p1["name"], p2["name"])

        return final_matches

    def _find_valid_pair(self, pool1: list, pool2: list, forbidden_group: str) -> tuple:
        """
        Pokusí se najít platný pár hráčů (jeden z pool1, druhý z pool2),
        kteří nejsou ze stejné skupiny a ani jeden není ze zakázané skupiny.
        Vrací (hráč1, hráč2, index1, index2) nebo (None, None, -1, -1).
        """
        if not pool1 or not pool2:
            return None, None, -1, -1

        for i, c1 in enumerate(pool1):
            if c1["group"] == forbidden_group:
                continue

            # Pokud hledáme ve stejném seznamu (pool1 je stejný objekt jako pool2),
            # musíme začít hledat od dalšího hráče, abychom nespárovali hráče se sebou samým
            start_j = i + 1 if pool1 is pool2 else 0

            for j in range(start_j, len(pool2)):
                c2 = pool2[j]
                if c2["group"] != c1["group"] and c2["group"] != forbidden_group:
                    return c1, c2, i, j

        return None, None, -1, -1