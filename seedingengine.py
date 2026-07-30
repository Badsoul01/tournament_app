class SeedingEngine:

    def __init__(self,tournament_format: str):
        self.tournament_format: str = tournament_format

    # ==========================================
    # VEŘEJNÉ API (HLAVNÍ METODY)
    # ==========================================

    def build_first_round(self,groups: dict, players: list = None, advance_per_group: int) -> list:
        """
        Hlavní metoda, která funguje jako vyhybka.
        Podle formátu turnaje rozhodne, jaký matematický algoritmus se použije.
        """
        if self.tournament_format == "groups_and_playoff":
            return self._generate_grouped_bracket(groups, advance_per_group)

        elif self.tournament_format == "playoff":
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
        # 1. Zjistíme velikost pavouka (nejbližší mocnina dvou)
        bracket_size = 2

        while bracket_size < len(players):
            bracket_size *= 2

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

        bracket = [0,1]
        while len(bracket) < size:
            next_bracket = []
            length = len(bracket) * 2

            for seed in bracket:
                next_bracket.append(seed)
                next_bracket.append(length - 1- seed)

            bracket = next_bracket

        return bracket

    def _calculating_byes(self, total_slots: int) -> int:
        """
        Spočítá počet potřebných volných lusů(BYE) bez nutnosti znát hráče.
        """
        size_of_bracket = 2
        while size_of_bracket < total_slots:
            size_of_bracket *= 2
        return size_of_bracket - total_slots

    def _generate_grouped_bracket(self,groups: dict, advance_per_group: int) -> list:
        """
        Připrava pro nový algoritmus
        """
        pass