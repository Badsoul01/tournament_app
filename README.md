# Tournament App

Webová aplikace vytvořená v Pythonu pro správu a organizaci turnajů (vhodná např. pro stolní tenis a jiné sporty). Systém umožňuje snadnou správu hráčů, automatické generování skupin i vyřazovacího pavouka (play-off) a přehledný export výsledků.

### 🌐 Živá aplikace

Aplikace běží online na: [www.spravaturnaje.cz](https://www.spravaturnaje.cz)


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
├── app/                      # Hlavní aplikační balíček
│   ├── __init__.py           # Application Factory (create_app, inicializace Flasku a rozšíření)
│   │
│   ├── models/               # 🗄️ Datová vrstva (SQLAlchemy)
│   │   ├── __init__.py       
│   │   └── models.py         # ORM modely (Tournament, Player, Group, Match, Bracket, Stats) vč. CheckConstraints
│   │
│   ├── services/             # ⚙️ Herní engine a business logika
│   │   ├── __init__.py       
│   │   ├── groupmanager.py   # Logika základních skupin (Round-Robin výpočty, řazení)
│   │   ├── playoff.py        # Generování vyřazovacího pavouka a zpracování postupů (vč. BYE logiky)
│   │   ├── seedingengine.py  # Algoritmy pro automatické nasazování (seeding) a prevenci kolizí
│   │   ├── player.py         # Pomocné výpočty a agregace hráčských statistik
│   │   ├── tournament.py     # Orchestrátor fází turnaje (přechody mezi skupinami a play-off)
│   │   ├── match.py          # Zpracování výsledků zápasů a validace
│   │   └── setupwizard.py    # Průvodce založením turnaje (konfigurace skupin a hráčů)
│   │
│   ├── web/                  # 🌐 Webová prezentační vrstva
│   │   ├── __init__.py       
│   │   ├── routes.py         # Flask HTTP endpointy a controller logika
│   │   └── webmanager.py     # Příprava dat pro šablony a logika exportu (.xlsx)
│   │
│   ├── templates/            # 🎨 Jinja2 šablony
│   │   ├── layout.html       # Hlavní layout aplikace
│   │   ├── index.html        # Seznam turnajů a dashboard
│   │   ├── tournament.html   # Detail konkrétního turnaje
│   │   └── partials/         # Modulární HTML komponenty pro HTMX
│   │       ├── _group_content.html # Dynamický obsah skupin
│   │       ├── _bracket.html       # Vykreslení play-off pavouka
│   │       └── _match_row.html     # Jednotlivý zápas pro úpravy výsledků
│   │
│   └── static/               # 📄 Klientské prostředky
│       ├── css/
│       │   └── style.css     # Kaskádové styly pro UI
│       └── js/
│           └── main.js       # Doplňkový JavaScript (HTMX eventy)
│
├── migrations/               # 🔄 Databázové migrace (Flask-Migrate / Alembic)
├── .env.example              # Vzorový konfigurační soubor pro lokální vývoj
├── .gitignore                # Pravidla pro ignorované soubory (.venv, __pycache__, atd.)
├── config.py                 # Globální nastavení Flasku a konstant
├── README.md                 # Tato dokumentace
├── requirements.txt          # Specifikace Python závislostí
└── run.py                    # 🚀 Vstupní bod pro lokální server i produkční Gunicorn (Render)
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
Vytvoř soubor `.env` v kořenovém adresáři (můžeš zkopírovat `.env.example`):
```bash
cp .env.example .env
````
A uprav v něm přístup k databázi a tajný klíč:
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