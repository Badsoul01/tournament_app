import sqlalchemy
from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload

from app.models.models import (
    Match as MatchModel,
    Player as PlayerModel,
    MatchResults as MatchResultsModel,
    GlobalPlayer as GlobalPlayerModel,
)


class MatchStatsService:

    @staticmethod
    def get_match_detail_context(match_id: int) -> dict:
        """
        Data pro rozbalovací detail konkrétního zápasu.

        Důležité:
        - sety se berou přímo z daného zápasu,
        - Win Rate se počítá živě ze všech dokončených zápasů hráče,
        - H2H se počítá živě ze všech dokončených vzájemných zápasů,
        - nic se tím nezapisuje do GlobalPlayer statistik.
        """
        match = MatchModel.query.get_or_404(match_id)

        sets = (
            match.sets.order_by(MatchResultsModel.set_number).all()
            if hasattr(match, "sets")
            else []
        )

        stats_a = MatchStatsService._get_live_player_stats(match.player_a)
        stats_b = MatchStatsService._get_live_player_stats(match.player_b)

        h2h_data = MatchStatsService.calculate_live_h2h_balance(
            match.player_a,
            match.player_b,
        )

        return {
            "match": match,
            "sets": sets,
            "stats_a": stats_a,
            "stats_b": stats_b,
            "h2h_data": h2h_data,
        }

    # ============================================================
    # LIVE STATISTIKY PRO DETAIL ZÁPASU
    # ============================================================

    @staticmethod
    def _resolve_global_player_id(player):
        """
        Vrátí global_player_id pro lokálního hráče.

        U rozehraného / neuzamčeného turnaje nemusí být lokální Player ještě
        propojený s GlobalPlayer. V takovém případě zkusíme bezpečný fallback
        podle přesného jména, ale pouze pokud existuje právě jeden GlobalPlayer
        s tímto jménem.
        """
        if not player:
            return None

        if player.global_player_id:
            return player.global_player_id

        if not player.name:
            return None

        candidates = GlobalPlayerModel.query.filter_by(name=player.name).all()

        if len(candidates) == 1:
            return candidates[0].id

        return None

    @staticmethod
    def _identity_condition(player_alias, player, resolved_global_id):
        """
        SQL podmínka pro identitu hráče.

        Aktuální lokální player.id zahrne i rozehraný turnaj.
        global_player_id zahrne jeho záznamy z předchozích turnajů.
        """
        conditions = []

        if player:
            conditions.append(player_alias.id == player.id)

        if resolved_global_id:
            conditions.append(
                player_alias.global_player_id == resolved_global_id
            )

        if not conditions:
            return False

        return or_(*conditions)

    @staticmethod
    def _get_live_player_stats(player):
        """
        Spočítá aktuální Win Rate přímo z dokončených Match záznamů.

        Nečeká na uzamčení turnaje a nijak nemění GlobalPlayer.
        """
        if not player:
            return {
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
            }

        resolved_global_id = MatchStatsService._resolve_global_player_id(player)

        PlayerA = sqlalchemy.orm.aliased(PlayerModel)
        PlayerB = sqlalchemy.orm.aliased(PlayerModel)

        identity_a = MatchStatsService._identity_condition(
            PlayerA,
            player,
            resolved_global_id,
        )
        identity_b = MatchStatsService._identity_condition(
            PlayerB,
            player,
            resolved_global_id,
        )

        matches = (
            MatchModel.query
            .options(
                joinedload(MatchModel.player_a),
                joinedload(MatchModel.player_b),
            )
            .join(PlayerA, MatchModel.player_a_id == PlayerA.id)
            .join(PlayerB, MatchModel.player_b_id == PlayerB.id)
            .filter(
                or_(identity_a, identity_b),
                MatchModel.is_finished == True,
            )
            .all()
        )

        wins = 0
        losses = 0
        draws = 0

        for match in matches:
            is_player_a = MatchStatsService._player_matches_identity(
                match.player_a,
                player,
                resolved_global_id,
            )

            our_local_id = (
                match.player_a_id
                if is_player_a
                else match.player_b_id
            )

            if match.winner_id is None:
                draws += 1
            elif match.winner_id == our_local_id:
                wins += 1
            else:
                losses += 1

        played = wins + losses + draws
        win_rate = (
            round((wins / played) * 100, 1)
            if played > 0
            else 0
        )

        return {
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
        }

    @staticmethod
    def _player_matches_identity(
        candidate_player,
        reference_player,
        resolved_global_id,
    ) -> bool:
        if not candidate_player:
            return False

        if (
            reference_player
            and candidate_player.id == reference_player.id
        ):
            return True

        if (
            resolved_global_id
            and candidate_player.global_player_id == resolved_global_id
        ):
            return True

        return False

    @staticmethod
    def calculate_live_h2h_balance(player_a, player_b):
        """
        Aktuální H2H pro dva lokální Player záznamy.

        Používá se hlavně v detailu konkrétního zápasu. Výpočet zahrne i
        dokončené zápasy z rozehraného turnaje a nic nezapisuje do GlobalPlayer.
        """
        if not player_a or not player_b:
            return MatchStatsService._empty_h2h()

        global_id_a = MatchStatsService._resolve_global_player_id(player_a)
        global_id_b = MatchStatsService._resolve_global_player_id(player_b)

        return MatchStatsService._calculate_live_h2h(
            reference_player_a=player_a,
            reference_player_b=player_b,
            global_id_a=global_id_a,
            global_id_b=global_id_b,
        )

    @staticmethod
    def calculate_live_h2h_for_global_players(global_player_a, global_player_b):
        if not global_player_a or not global_player_b:
            return MatchStatsService._empty_h2h()

        PlayerA = sqlalchemy.orm.aliased(PlayerModel)
        PlayerB = sqlalchemy.orm.aliased(PlayerModel)

        # Hráč A může být:
        # 1) už propojen přes global_player_id
        # 2) ještě nepropojený hráč z rozehraného turnaje,
        #    kterého poznáme podle přesného jména
        player_a_condition = or_(
            PlayerA.global_player_id == global_player_a.id,
            and_(
                PlayerA.global_player_id.is_(None),
                PlayerA.name == global_player_a.name
            )
        )

        player_b_condition = or_(
            PlayerB.global_player_id == global_player_b.id,
            and_(
                PlayerB.global_player_id.is_(None),
                PlayerB.name == global_player_b.name
            )
        )

        # Obrácené postavení A/B v zápase
        player_b_as_a_condition = or_(
            PlayerA.global_player_id == global_player_b.id,
            and_(
                PlayerA.global_player_id.is_(None),
                PlayerA.name == global_player_b.name
            )
        )

        player_a_as_b_condition = or_(
            PlayerB.global_player_id == global_player_a.id,
            and_(
                PlayerB.global_player_id.is_(None),
                PlayerB.name == global_player_a.name
            )
        )

        matches = (
            MatchModel.query
            .options(
                joinedload(MatchModel.player_a),
                joinedload(MatchModel.player_b),
                joinedload(MatchModel.tournament),
            )
            .join(PlayerA, MatchModel.player_a_id == PlayerA.id)
            .join(PlayerB, MatchModel.player_b_id == PlayerB.id)
            .filter(
                or_(
                    and_(
                        player_a_condition,
                        player_b_condition
                    ),
                    and_(
                        player_b_as_a_condition,
                        player_a_as_b_condition
                    )
                ),
                MatchModel.is_finished == True
            )
            .all()
        )

        wins_a = 0
        wins_b = 0
        draws = 0
        match_history = []

        for match in matches:

            is_a_player_a = (
                    match.player_a.global_player_id == global_player_a.id
                    or (
                            match.player_a.global_player_id is None
                            and match.player_a.name == global_player_a.name
                    )
            )

            our_local_id = (
                match.player_a_id
                if is_a_player_a
                else match.player_b_id
            )

            if match.winner_id is None:
                draws += 1
                result_for_a = "R"

            elif match.winner_id == our_local_id:
                wins_a += 1
                result_for_a = "V"

            else:
                wins_b += 1
                result_for_a = "P"

            match_history.append({
                "tournament_name":
                    match.tournament.name if match.tournament else "-",

                "tournament_id":
                    match.tournament.id if match.tournament else None,

                "phase":
                    match.phase_display_name
                    if hasattr(match, "phase_display_name")
                    else "-",

                "score":
                    match.formatted_score
                    if hasattr(match, "formatted_score")
                    else "-",

                "result_for_a": result_for_a,
                "raw_match": match,
            })

        total = wins_a + wins_b + draws

        win_rate_a = (
            round((wins_a / total) * 100, 1)
            if total > 0
            else 0
        )

        return {
            "wins_a": wins_a,
            "wins_b": wins_b,
            "draws": draws,
            "total": total,
            "win_rate_a": win_rate_a,
            "matches": match_history,
        }

    @staticmethod
    def _empty_h2h():
        return {
            "wins_a": 0,
            "wins_b": 0,
            "draws": 0,
            "total": 0,
            "win_rate_a": 0,
            "matches": [],
        }

    @staticmethod
    def _calculate_live_h2h(
        reference_player_a,
        reference_player_b,
        global_id_a,
        global_id_b,
    ):
        """
        Společné jádro živého H2H výpočtu.

        Identita hráče je tvořena kombinací:
        - konkrétního lokálního Player.id, pokud je k dispozici,
        - global_player_id napříč předchozími turnaji.

        Díky tomu detail zápasu zahrne i aktuální lokální záznam z rozehraného
        turnaje a profil hráče zároveň vidí všechny lokální záznamy napojené na
        daný GlobalPlayer.
        """
        if (
            not global_id_a
            and not reference_player_a
        ) or (
            not global_id_b
            and not reference_player_b
        ):
            return MatchStatsService._empty_h2h()

        PlayerA = sqlalchemy.orm.aliased(PlayerModel)
        PlayerB = sqlalchemy.orm.aliased(PlayerModel)

        a_on_a = MatchStatsService._identity_condition(
            PlayerA,
            reference_player_a,
            global_id_a,
        )
        b_on_b = MatchStatsService._identity_condition(
            PlayerB,
            reference_player_b,
            global_id_b,
        )
        b_on_a = MatchStatsService._identity_condition(
            PlayerA,
            reference_player_b,
            global_id_b,
        )
        a_on_b = MatchStatsService._identity_condition(
            PlayerB,
            reference_player_a,
            global_id_a,
        )

        matches = (
            MatchModel.query
            .options(
                joinedload(MatchModel.player_a),
                joinedload(MatchModel.player_b),
                joinedload(MatchModel.tournament),
            )
            .join(PlayerA, MatchModel.player_a_id == PlayerA.id)
            .join(PlayerB, MatchModel.player_b_id == PlayerB.id)
            .filter(
                or_(
                    and_(a_on_a, b_on_b),
                    and_(b_on_a, a_on_b),
                ),
                MatchModel.is_finished == True,
            )
            .all()
        )

        wins_a = 0
        wins_b = 0
        draws = 0
        match_history = []

        for match in matches:
            is_a_in_a = MatchStatsService._player_matches_identity(
                match.player_a,
                reference_player_a,
                global_id_a,
            )

            our_local_id = (
                match.player_a_id
                if is_a_in_a
                else match.player_b_id
            )

            if match.winner_id is None:
                draws += 1
                result_for_a = "R"
            elif match.winner_id == our_local_id:
                wins_a += 1
                result_for_a = "V"
            else:
                wins_b += 1
                result_for_a = "P"

            tournament_id = None
            tournament_name = "-"

            if match.tournament:
                tournament_id = match.tournament.id
                tournament_name = match.tournament.name

            match_history.append({
                "tournament_name": tournament_name,
                "tournament_id": tournament_id,
                "phase": (
                    match.phase_display_name
                    if hasattr(match, "phase_display_name")
                    else "-"
                ),
                "score": (
                    match.formatted_score
                    if hasattr(match, "formatted_score")
                    else "-"
                ),
                "result_for_a": result_for_a,
                "raw_match": match,
            })

        total = wins_a + wins_b + draws
        win_rate_a = (
            round((wins_a / total) * 100, 1)
            if total > 0
            else 0
        )

        return {
            "wins_a": wins_a,
            "wins_b": wins_b,
            "draws": draws,
            "total": total,
            "win_rate_a": win_rate_a,
            "matches": match_history,
        }

    # ============================================================
    # OFICIÁLNÍ / GLOBÁLNÍ H2H
    # ============================================================
    #
    # Tyto dvě metody necháváme zachované, protože PlayerStatsService je
    # používá pro H2H záložku hráče.

    @staticmethod
    def calculate_h2h_balance(
        global_id_a: int,
        global_id_b: int,
        up_to_match_id: int = None,
    ):
        """Univerzální metoda pro výpočet bilance mezi dvěma GlobalPlayer."""
        if not global_id_a or not global_id_b:
            return {
                "wins_a": 0,
                "wins_b": 0,
                "draws": 0,
                "total": 0,
                "win_rate_a": 0,
                "matches": [],
            }

        past_matches = MatchStatsService.get_h2h_matches(
            global_id_a,
            global_id_b,
            up_to_match_id=up_to_match_id,
        )

        wins_a = 0
        wins_b = 0
        draws = 0
        match_history = []

        for hm in past_matches:
            is_a_in_a = (
                hm.player_a
                and hm.player_a.global_player_id == global_id_a
            )

            our_local_id = (
                hm.player_a_id
                if is_a_in_a
                else hm.player_b_id
            )

            if hm.winner_id is None:
                draws += 1
                res_for_a = "R"
            elif hm.winner_id == our_local_id:
                wins_a += 1
                res_for_a = "V"
            else:
                wins_b += 1
                res_for_a = "P"

            tournament_id = None
            tournament_name = "-"

            if hm.tournament:
                tournament_id = hm.tournament.id
                tournament_name = hm.tournament.name

            match_history.append({
                "tournament_name": tournament_name,
                "tournament_id": tournament_id,
                "phase": (
                    hm.phase_display_name
                    if hasattr(hm, "phase_display_name")
                    else "-"
                ),
                "score": (
                    hm.formatted_score
                    if hasattr(hm, "formatted_score")
                    else "-"
                ),
                "result_for_a": res_for_a,
                "raw_match": hm,
            })

        total = wins_a + wins_b + draws
        win_rate_a = (
            round((wins_a / total) * 100, 1)
            if total > 0
            else 0
        )

        return {
            "wins_a": wins_a,
            "wins_b": wins_b,
            "draws": draws,
            "total": total,
            "win_rate_a": win_rate_a,
            "matches": match_history,
        }

    @staticmethod
    def get_h2h_matches(
        global_id_a: int,
        global_id_b: int,
        up_to_match_id: int = None,
    ):
        """
        Vrátí všechny dokončené vzájemné zápasy dvou GlobalPlayer.

        Tato metoda zůstává kvůli PlayerStatsService.
        """
        PlayerA = sqlalchemy.orm.aliased(PlayerModel)
        PlayerB = sqlalchemy.orm.aliased(PlayerModel)

        query = (
            MatchModel.query
            .options(
                joinedload(MatchModel.player_a),
                joinedload(MatchModel.player_b),
                joinedload(MatchModel.tournament),
            )
            .join(PlayerA, MatchModel.player_a_id == PlayerA.id)
            .join(PlayerB, MatchModel.player_b_id == PlayerB.id)
            .filter(
                or_(
                    and_(
                        PlayerA.global_player_id == global_id_a,
                        PlayerB.global_player_id == global_id_b,
                    ),
                    and_(
                        PlayerA.global_player_id == global_id_b,
                        PlayerB.global_player_id == global_id_a,
                    ),
                ),
                MatchModel.is_finished == True,
            )
        )

        if up_to_match_id:
            query = query.filter(MatchModel.id <= up_to_match_id)

        return query.all()
