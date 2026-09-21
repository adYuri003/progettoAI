from dotenv import load_dotenv

# Carica le variabili da .env (in particolare GOOGLE_API_KEY).
# Importante: deve avvenire PRIMA degli import di Agno.
load_dotenv()

from pydantic import BaseModel, Field
import json
from pathlib import Path
from agno.agent import Agent
from agno.models.google import Gemini
from agno.db.sqlite import SqliteDb
from agno.os import AgentOS
from agno.tools import tool
from agno.tools.reasoning import ReasoningTools
from agno.knowledge.knowledge import Knowledge
from agno.knowledge.embedder.google import GeminiEmbedder
from agno.vectordb.lancedb import LanceDb, SearchType
from agno.learn import (
    LearningMachine,
    LearningMode,
    UserProfileConfig,
    UserMemoryConfig,
)

# region Costanti e setup

RECIPES_DB = [
    {
        "name": "Insalata di ceci e zucchine",
        "ingredients": ["ceci", "zucchine", "limone", "olio"],
        "minutes": 15,
        "tags": ["vegetariano", "vegano", "senza-glutine"],
    },
    {
        "name": "Riso allo yogurt e zucchine",
        "ingredients": ["riso", "zucchine", "yogurt-greco", "olio"],
        "minutes": 25,
        "tags": ["vegetariano", "senza-glutine"],
    },
    {
        "name": "Pasta al pesto di rucola",
        "ingredients": ["pasta", "rucola", "parmigiano", "noci"],
        "minutes": 20,
        "tags": ["vegetariano", "contiene-frutta-secca"],
    },
    {
        "name": "Hummus express",
        "ingredients": ["ceci", "limone", "tahini", "aglio"],
        "minutes": 10,
        "tags": ["vegetariano", "vegano", "senza-glutine"],
    },
]

SHOPPING_LIST_FILE = Path("tmp/shopping_list.json")

# endregion

# region Tools


@tool
def find_recipes_by_constraints(
    available_ingredients: list[str],
    dietary_constraints: list[str] = [],
    max_minutes: int = 60,
) -> list[dict]:
    """Trova ricette compatibili con ingredienti disponibili, vincoli e tempo.

    Tool READ-ONLY (rischio basso): non modifica nessuno stato esterno.

    Args:
        available_ingredients: ingredienti che l'utente ha a disposizione.
        dietary_constraints: tag dietetici richiesti, es. ["vegetariano", "vegano"].
        max_minutes: tempo massimo di preparazione in minuti.

    Returns:
        Lista di ricette compatibili.
    """
    available_set = set(i.lower() for i in available_ingredients)
    constraints_set = set(c.lower() for c in dietary_constraints)

    results = []
    for recipe in RECIPES_DB:
        if recipe["minutes"] > max_minutes:
            continue
        if constraints_set and not constraints_set.issubset(set(recipe["tags"])):
            continue
        recipe_ingredients = set(i.lower() for i in recipe["ingredients"])
        if not recipe_ingredients.issubset(available_set):
            missing = recipe_ingredients - available_set
            if len(missing) > 2:
                continue
        results.append(recipe)

    return results


@tool
def save_shopping_list(items: list[str]) -> str:
    """Salva la lista della spesa su file.

    Tool STATE UPDATE (rischio medio): modifica un file persistente.

    Args:
        items: lista di ingredienti da acquistare.

    Returns:
        Messaggio di conferma con il numero di item salvati.
    """
    SHOPPING_LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHOPPING_LIST_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    return f"Lista della spesa salvata con {len(items)} ingredienti in {SHOPPING_LIST_FILE}."


# endregion

# region Models


class RecipeRecommendation(BaseModel):
    """Risposta strutturata di RecipeBot."""

    selected_recipe: str = Field(description="Nome della ricetta scelta.")
    estimated_minutes: int = Field(description="Tempo di preparazione in minuti.")
    missing_ingredients: list[str] = Field(
        default_factory=list,
        description="Ingredienti che l'utente deve comprare per fare questa ricetta.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Avvisi rilevanti per l'utente: allergeni potenziali, "
            "vincoli a rischio, conflitti dietetici."
        ),
    )
    reason: str = Field(
        description="Breve spiegazione del perché questa ricetta è stata scelta."
    )


# endregion

# Knowledge Base

knowledge = Knowledge(
    vector_db=LanceDb(
        table_name="recipebot_knowledge",
        uri="tmp/lancedb",
        search_type=SearchType.vector,
        embedder=GeminiEmbedder(),
    ),
)

# Inserimento idempotente: se i file non sono cambiati, è veloce.
knowledge.insert(path="docs/ricettario.md")
knowledge.insert(path="docs/allergeni.md")

# endregion

db = SqliteDb(db_file="tmp/recipebot.db")

recipebot = Agent(
    name="RecipeBot",
    description="Assistente di cucina che propone ricette e gestisce la lista della spesa.",
    model=Gemini(id="gemini-2.5-flash"),
    db=db,
    instructions=[
        "Sei RecipeBot, un assistente di cucina.",
        "Distingui i vincoli HARD (allergie, diete) dalle preferenze SOFT (gusti).",
        "Non suggerire mai ingredienti che violino le allergie dichiarate dall'utente.",
        "Quando l'utente non specifica un vincolo, chiedi prima di assumere.",
        "Per richieste con più vincoli, usa think() per decomporli prima di agire.",
        "Dopo aver chiamato find_recipes_by_constraints, usa analyze() per valutare i risultati.",
        "Se nessuna ricetta soddisfa i vincoli, segnala il conflitto in warnings.",
        "Usa find_recipes_by_constraints per cercare ricette compatibili.",
        "Usa save_shopping_list quando l'utente chiede di salvare gli ingredienti mancanti.",
        "Restituisci sempre una raccomandazione strutturata secondo lo schema RecipeRecommendation.",
        "Consulta la knowledge base per: tecniche di cottura, allergeni, sostituzioni di ingredienti.",
        "Quando l'utente menziona allergie, preferenze o caratteristiche personali, salva queste informazioni nei tool di learning per ricordarle nelle conversazioni future.",
    ],
    tools=[
        ReasoningTools(add_instructions=True),
        find_recipes_by_constraints,
        save_shopping_list,
    ],
    knowledge=knowledge,
    search_knowledge=True,
    # output_schema=RecipeRecommendation,
    # use_json_mode=True,
    learning=LearningMachine(
        user_profile=UserProfileConfig(mode=LearningMode.AGENTIC),
        user_memory=UserMemoryConfig(mode=LearningMode.AGENTIC),
    ),
    # La memoria resta scrivibile, ma non contamina le demo diagnostiche.
    add_learnings_to_context=False,
    add_history_to_context=True,
    num_history_runs=3,
    debug_mode=True,
    markdown=True,
)

agent_os = AgentOS(
    name="RecipeBot OS",
    agents=[recipebot],
    db=db,
    tracing=True,
)

app = agent_os.get_app()
