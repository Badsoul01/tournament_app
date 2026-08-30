Markdown
# Tournament App

Webová aplikace vytvořená v Pythonu pro správu a organizaci turnajů (vhodná např. pro stolní tenis a jiné sporty). Systém umožňuje snadnou správu hráčů, automatické generování skupin i vyřazovacího pavouka (play-off) a přehledný export výsledků.

## 🚀 Hlavní funkce

* **Správa turnajů a hráčů:** Registrace účastníků, rozřazování do skupin a sledování stavu zápasů.
* **Dynamické rozhraní:** Využití HTMX pro rychlou interaktivitu bez nutnosti zbytečného načítání celé stránky.
* **Generování pavouka:** Automatické nasazování hráčů ze základních skupin do vyřazovacích bojů.
* **Export dat:** Možnost exportu výsledků a tabulek do formátu Excel (`.xlsx`) pomocí knihovny OpenPYXL.

## 🛠️ Použité technologie

* **Backend:** Python, Flask
* **Databáze:** PostgreSQL, SQLAlchemy (ORM)
* **Frontend:** HTML, CSS, HTMX
* **Ostatní:** OpenPYXL (export do Excelu)

## 📁 Struktura projektu

```text
tournament_app/
├── app/
│   ├── __init__.py           # Application Factory (create_app, inicializace Flasku)
│   ├── models/               # Databázové ORM modely (SQLAlchemy)
│   │   ├── __init__.py       # Balíček pro modely (prázdný)
│   │   └── models.py         # Modely (Tournament, Group, Player, Match, Bracket, Stats)
│   │
│   ├── services/             # Herní logika a algoritmy (Game Engine)
│   │   ├── __init__.py       # Balíček pro služby (prázdný)
│   │   ├── groupmanager.py   # Správa a výpočty skupin (Round-Robin)
│   │   ├── playoff.py        # Logika vyřazovacího pavouka a posun hráčů
│   │   ├── seedingengine.py  # Algoritmus nasazování hráčů & hlídání kolizí skupin
│   │   ├── player.py         # Pomocné výpočty statistik a řazení hráčů (PlayerHelper)
│   │   ├── tournament.py     # Orchestrátor vytváření turnaje a jeho dokončení
│   │   ├── match.py          # Vyhodnocování zápasů a přepínání stavů
│   │   └── setupwizard.py    # Průvodce nastavením nového turnaje
│   │
│   ├── web/                  # Prezentace, routy & Web Management
│   │   ├── __init__.py       # Balíček pro webovou vrstvu (prázdný)
│   │   ├── routes.py         # Flask HTTP endpointy (původně main.py)
│   │   └── webmanager.py     # Data pro HTML šablony + generování Excel exportu
│   │
│   └── templates/            # HTML šablony (Jinja2)
│       └── partials/         # HTML komponenty pro HTMX (_group_content.html, ...)
│
├── migrations/               # Databázové migrace (Flask-Migrate / Alembic)
├── .env                      # Lokální proměnné prostředí (ignorováno v Gitu)
├── .env.example              # Vzorový konfigurační soubor s proměnnými
├── .gitignore                # Ignorované soubory (.venv, .idea, __pycache__)
├── config.py                 # Globální pravidla a konfigurace turnajů
├── README.md                 # Dokumentace projektu
├── requirements.txt          # Seznam závislostí projektu
└── run.py                    # Vstupní bod pro spuštění aplikace (from app import create_app)
```

## 🔧 Instalace a spuštění

### 1. Klonování repozitáře
```bash
git clone [https://github.com/Badsoul01/tournament_app.git](https://github.com/Badsoul01/tournament_app.git)
cd tournament_app
```

### 2. Vytvoření a aktivace virtuálního prostředí
```bash
python3 -m venv .venv
source .venv/bin/activate
```
### 3. Instalace závislostí
```bash
pip install -r requirements.txt
```

#### 3.1 Nastavení proměnných prostředí
Vytvoř soubor `.env` v kořenovém adresáři (můžeš zkopírovat .env.example]:
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/tournament_db
SECRET_KEY=tvoje_tajne_heslo
```
### 4. Nastavení databáze a spuštění
Ujisti se, že ti běží PostgreSQL databáze, a nastav připojovací řetězec v konfiguračním souboru nebo proměnných prostředí.

Spuštění aplikace:
``` bash
python run.py
```

Aplikace poběží na [http://127.0.0.1:5000/](http://127.0.0.1:5000/).

### 📝 Licence
Tento projekt je šířen pod licencí MIT.