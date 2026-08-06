import group


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


    def _generate_smart_grouped_bracket(self,groups: dict, start_rank: int, end_rank: int) -> list:
        """
        lineární/chytrý algoritmus pro nestandartní počty skupin
        Hlídá fixní BYE indexy a zamezuje kolizím v 2.kole.
        """
        pots = {}
        group_names = sorted(groups.keys())

        # 1. Sestavení dostupných slotů
        for group_name in group_names:
            players = groups[group_name]
            for rank_idx in range(start_rank, end_rank+1):
                # Kontrola, zuda skupina má dostatek hráčů pro tento rank
                if rank_idx - 1 < len(players):
                    slot_id = f"{rank_idx}{group_name}"
                    slot_info = {"name": slot_id,"group":group_name,"rank":rank_idx}
                    pots.setdefault(rank_idx,[]).append(slot_info)

        all_advancing = [slot for pot in pots.values() for slot in pot]
        total_slot_count = len(all_advancing)
        bracket_size,byes_count = self._get_smart_bracket_config(total_slot_count)

        total_matches = bracket_size //2
        final_matches = [None] * total_matches

        if total_matches == 4:
            if byes_count == 1:
                byes_indices = [0]
            elif byes_count == 2:
                byes_indices = [0, 3]  # První a poslední zápas (vrchol a dno pavouka)

            else:
                byes_indices = list(range(byes_count))

        elif total_matches == 8:
            if byes_count == 1:
                byes_indices = [0]
            elif byes_count == 2:
                byes_indices = [0,7]
            elif byes_count == 3:
                byes_indices = [0,3,7]
            elif byes_count == 4:
                byes_indices = [0,3,4,7]
            else:
                byes_indices = list(range(byes_count))
        else:
            byes_indices = list(range(byes_count))

        # Dynamicky najdeme nejvyšší možný rank v tomto pavouku
        top_rank =  min(pots.keys()) if pots else start_rank
        top_pot = pots.get(top_rank, []).copy()

        worst_rank = max(pots.keys()) if pots else  start_rank
        worst_pool = pots.get(worst_rank, []).copy()


        assigned_slots = {}
        # Definice kotevních pozic pro jednotlivé skupiny
        anchor_map = {
            "A":0,
            "B": total_matches -1,
        }
        if total_matches >=8:
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
                    # Spárování s nejhorším dostupným soupěřem z worst_pool
                    p2 = next((w for w in worst_pool if w["group"] != group_letter), None)
                    if not p2 and worst_pool:
                        p2 = worst_pool[0]
                    if p2:
                        worst_pool.remove(p2)
                        assigned_slots[idx] = (slot_info["name"], p2["name"])
                    else:
                        assigned_slots[idx] = (slot_info["name"], None)

       # Doplnění zbývajících BYE Slotů
        for idx in byes_indices:
            if idx not in assigned_slots and top_pot:
                slot_info = top_pot.pop(0)
                assigned_slots[idx] = (slot_info["name"],None)

        for idx, match in assigned_slots.items():
            final_matches[idx]= match

        used_player_names = set()
        for match in final_matches:
            if match is not None:
                if match[0]:
                    used_player_names.add(match[0])
                if match[1]:
                    used_player_names.add(match[1])

        # 4. Přípraga zbytku na párování
        active_pot_1 = [s for s in pots.get(top_rank,[]) if s["name"] not in used_player_names]

        lower_pool = []
        for rank in range(end_rank, 1, -1):
            for s in pots.get(rank,[]):
                if s["name"] not in used_player_names:
                    lower_pool.append(s)

        normal_slots = [i for i in range(total_matches) if final_matches[i] is None]

        mid = total_matches // 2
        top_normals = [s for s in normal_slots if s < mid]
        bottom_normals = [s for s in normal_slots if s >= mid]

        iterleaved_slots = []
        for t, b in zip(top_normals,bottom_normals):
            iterleaved_slots.append(t)
            iterleaved_slots.append(b)

        # kdybychom měli v jedné polovině více  slotů, zbytek připojíme nakonec
        if len(top_normals) > len(bottom_normals):
            iterleaved_slots.extend(top_normals[len(bottom_normals):])
        elif len(bottom_normals)> len(top_normals):
            iterleaved_slots.extend(bottom_normals[len(top_normals):])


        # 5. Párování zbývajících slotů s ohledme na kolive ve 2.kole (s ^ 1)
        for s in iterleaved_slots:
            partner_slot = s ^ 1
            forbidden_group = None
            if partner_slot < len(final_matches) and final_matches[partner_slot] is not None:
                # Zjistíme skupinu ze sousedního slotu (pokud to není BYE)
                partner_match = final_matches[partner_slot]
                if partner_match[0] is not None:
                    #Zjistíme písmenko skupiny z násvu slotu
                    forbidden_group = partner_match[0][-1]

            p1, p2 = None, None

            # Strategie A : křížové párování (zbylá 1.místa vs 2+ místa)
            if active_pot_1 and lower_pool:
                for i, c1 in enumerate(active_pot_1):
                    if c1["group"]== forbidden_group:
                        continue
                    for j, c2 in enumerate(lower_pool):
                        if c2["group"] != c1["group"] and c2["group"] != forbidden_group:
                            p1, p2 = c1, c2
                            active_pot_1.pop(i)
                            lower_pool.pop(j)
                            break
                    if p1:
                        break

            # Strategie B: pokud došla 1.místa
            if not p1 and len(lower_pool) >= 2:
                for i, c1 in enumerate(lower_pool):
                    if c1["group"] == forbidden_group:
                        continue
                    for j, c2 in enumerate(lower_pool):
                        if i != j and c2["group"] != c1["group"] and c2["group"] != forbidden_group:
                            p1, p2 = c1, c2
                            for idx_to_rem in sorted([i, j], reverse=True):
                                lower_pool.pop(idx_to_rem)
                            break
                    if p1:
                        break

            # STRATEGIE C: Zbyly už pouze jedničky (velmi ojedinělá situace / pojistka)
            if not p1 and len(active_pot_1) >= 2:
                for i, c1 in enumerate(active_pot_1):
                    if c1["group"] == forbidden_group:
                        continue
                    for j, c2 in enumerate(active_pot_1):
                        if i != j and c2["group"] != c1["group"] and c2["group"] != forbidden_group:
                            p1, p2 = c1, c2
                            for idx_to_rem in sorted([i, j], reverse=True):
                                active_pot_1.pop(idx_to_rem)
                            break
                    if p1:
                        break

            # NOUZOVÁ POJISTKA: (např. zbydou 2 stejné skupiny, ignorujeme pravidla)
            if not p1:
                emergency_pool = active_pot_1 + lower_pool
                if len(emergency_pool) >= 2:
                    p1, p2 = emergency_pool[0], emergency_pool[1]
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



