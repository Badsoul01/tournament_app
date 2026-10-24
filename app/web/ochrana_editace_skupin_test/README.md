# První bezpečnostní oprava – ochrana před částečným uložením výsledků

Tento krok neřeší atomické transakce. Pouze **preventivně blokuje editaci skupiny** před jakýmkoli DB zápisem, pokud už existuje skutečně odehraný zápas playoff nebo útěchy. Automatická BYE ignoruje.

## Instalace – pouze lokální test
1. Zálohuj `app/web/webmanager.py`.
2. Nahraď jej zde dodaným souborem `webmanager.py`.
3. `match.py`, `groupmanager.py` a `playoff.py` zatím neměň (ponech předchozí funkční opravu BYE).
4. Zastav a spusť Flask, zkus test na kopií databáze.

## Testy
- Pouze vygenerovaný pavouk + BYE: skupinu jde odemknout a opravit.
- Skutečně odehraný playoff zápas: odemknutí skupiny musí být zablokováno a DB nezměněna.
- Ručně připravené čtvrtfinále bez výsledku: kontrola ho neblokuje, ale další interní kontrola enginu ho ještě může odmítnout — tato verze NEZAJIŠŤUJE rollback již commitnutých dat při pozdější výjimce.

## DŮLEŽITÉ
V současném `evaluate()` je commit před `GroupManager.handle_match_completion`, a další commity jsou rozeseté v enginu. K opravdové transakční bezpečnosti je nutné sjednotit hranice commitů v `match.py`, `groupmanager.py`, `playoff.py` a `PlayerHelper`, a až po úspěchu uložit změny jedním commitem. Tento balíček je **dočasný konzervativní guard**, ne definitivní oprava integrity.

Kvůli chybové hlášce může být potřeba upravit Flask route, která nyní neodchytává `ValueError` — v tomto prototypu chybu úmyslně nezamlčujeme.
