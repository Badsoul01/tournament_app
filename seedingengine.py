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

    def _generate_grouped_bracket(self,groups: dict, start_rank: int, end_rank: int) -> list:
        """
        Připrava pro nový algoritmus
        """
        # 1. Nasbíráme všechna postupová místa ze všech skupin
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

                if g is not None:
                    buckets[i].append(f"{rank}{g}")

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