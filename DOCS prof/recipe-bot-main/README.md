# recipe-bot

Assistente di cucina basato su [Agno](https://docs.agno.com/) e Google Gemini.
Espone un agente (`RecipeBot`) tramite [AgentOS](https://docs.agno.com/agent-os) servito da FastAPI: propone ricette compatibili con ingredienti, vincoli dietetici e tempo a disposizione, e gestisce una lista della spesa persistente.

## Prerequisiti

- **Python 3.12+** (vedi [.python-version](.python-version))
- **[uv](https://docs.astral.sh/uv/)** come package manager
- Una **API key di Google Gemini** (vedi sotto)

## 1. Ottenere una API key per Gemini

1. Vai su [Google AI Studio](https://aistudio.google.com/apikey).
2. Accedi con un account Google.
3. Clicca su **Create API key** e copia il valore generato (inizia con `AIza...`).
4. Tieni la chiave a portata di mano: ti servirà al passo 4.

> La chiave è personale e dà accesso a fatturazione/quote: non condividerla e non committarla.

## 2. Scaffolding iniziale (solo al primo setup di un progetto da zero)

Se stai creando il progetto da zero, in una cartella vuota lancia:

```powershell
uv init .
```

Questo crea `pyproject.toml`, `.python-version` e gli altri file base.

`uv init` genera anche un `main.py` di esempio: puoi cancellarlo, non viene usato dal progetto (il punto di ingresso è [recipebot.py](recipebot.py)).

> In questo repo lo scaffolding è già stato fatto: salta questo step e passa al successivo.

## 3. Creare il virtual environment e installare le dipendenze

Crea il venv:

```powershell
uv venv
```

Sincronizza le dipendenze dichiarate in [pyproject.toml](pyproject.toml) / [uv.lock](uv.lock):

```powershell
uv sync
```

Attiva il venv (PowerShell su Windows):

```powershell
.venv\Scripts\Activate.ps1
```

Su bash/zsh:

```bash
source .venv/bin/activate
```

## 4. Creare il file `.env`

Nella root del progetto crea un file `.env` con la chiave ottenuta al passo 1:

```dotenv
GOOGLE_API_KEY=la-tua-chiave-qui
```

Il file `.env` è già in [.gitignore](.gitignore): non verrà committato.
[recipebot.py](recipebot.py) lo carica automaticamente con `python-dotenv` prima di importare Agno.

## 5. Avviare il bot

Con il venv attivo:

```powershell
fastapi dev recipebot.py
```

Il server di sviluppo si avvia su `http://127.0.0.1:8000`. Endpoint utili:

- `http://127.0.0.1:8000/docs` — Swagger UI di FastAPI
- `http://127.0.0.1:8000` — root dell'AgentOS

Al primo avvio l'agente:

- crea il database SQLite in `tmp/recipebot.db`
- crea l'indice vettoriale LanceDB in `tmp/lancedb`
- ingerisce i file di knowledge da [docs/](docs/)

## Escludere `tmp/` da git

La cartella `tmp/` contiene stato runtime (db SQLite, vector store LanceDB, `shopping_list.json`) che non va versionato. Aggiungi al [.gitignore](.gitignore):

```gitignore
tmp/**
```

In questo repo l'esclusione è già presente. Se hai già committato per errore qualche file dentro `tmp/`, rimuovilo dall'indice mantenendolo su disco con:

```powershell
git rm -r --cached tmp
```

## Struttura del progetto

```
recipe-bot/
├── recipebot.py        # definizione agente, tools, AgentOS, app FastAPI
├── docs/               # knowledge base (ricettario, allergeni)
├── tmp/                # stato runtime: db, vector store, shopping list
├── pyproject.toml      # dipendenze
├── uv.lock             # lockfile uv
└── .env                # GOOGLE_API_KEY (NON committare)
```

## Troubleshooting

- **`GOOGLE_API_KEY` non trovata**: verifica che `.env` esista nella stessa cartella da cui lanci `fastapi dev` e che la variabile sia scritta senza spazi attorno a `=`.
- **`fastapi: command not found`**: il venv non è attivo, oppure `uv sync` non è stato eseguito.
- **Errori da LanceDB/Tantivy al primo avvio**: cancella la cartella `tmp/` e riavvia per rigenerare gli indici.
