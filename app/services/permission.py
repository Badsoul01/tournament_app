from flask import session


def can_edit_tournament(tournament):
    """Rozhodne, zda má aktuální uživatel (nebo guest) právo upravovat tento turnaj."""

    # 1. Je to přihlášený organizátor a turnaj mu patří?
    if 'organizer_id' in session and tournament.organizer_id == session['organizer_id']:
        return True

    # 2. Je to nepřihlášený "Guest", který turnaj založil v aktuální relaci?
    # Kontrolujeme, že turnaj zatím v databázi nikomu nepatří (organizer_id je None)
    if tournament.organizer_id is None and 'guest_tournaments' in session:
        if tournament.id in session['guest_tournaments']:
            return True

    # Pokud ani jedno neplatí, přístup zamítnut
    return False