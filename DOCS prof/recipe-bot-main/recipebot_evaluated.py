from dotenv import load_dotenv

# Carica le variabili da .env (in particolare GOOGLE_API_KEY).
# Importante: deve avvenire PRIMA degli import di Agno.
load_dotenv()

from pydantic import BaseModel, Field
import json
from pathlib import Path
from typing import Any
from agno.agent import Agent
from agno.exceptions import CheckTrigger, OutputCheckError
from agno.eval.agent_as_judge import AgentAsJudgeEval
from agno.guardrails import PromptInjectionGuardrail
from agno.models.google import Gemini
from agno.db.sqlite import SqliteDb
from agno.os import AgentOS
from agno.team.mode import TeamMode
from agno.team.team import Team
from agno.run.team import TeamRunOutput
from agno.tools import tool
from agno.tools.reasoning import ReasoningTools
from agno.workflow.step import Step, StepInput, StepOutput
from agno.workflow.workflow import Workflow
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

PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore your instructions",
    "you are now a",
    "forget everything above",
    "developer mode",
    "override safety",
    "disregard guidelines",
    "system prompt",
    "jailbreak",
    "act as if",
    "pretend you are",
    "roleplay as",
    "simulate being",
    "bypass restrictions",
    "ignore safeguards",
    "admin override",
    "root access",
    "forget everything",
    "ignora le istruzioni",
    "dimentica che sei",
    "sei ora un assistente generico",
]

# endregion

# region Tools


def _find_recipes(
    available_ingredients: list[str],
    dietary_constraints: list[str],
    max_minutes: int,
) -> list[dict]:
    """Ricerca pura riusabile da tool e workflow."""
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
    return _find_recipes(available_ingredients, dietary_constraints, max_minutes)


@tool
def find_safe_recipes_by_constraints(
    available_ingredients: list[str],
    dietary_constraints: list[str] = [],
    excluded_ingredients: list[str] = [],
    max_minutes: int = 60,
) -> list[dict]:
    """Trova ricette compatibili escludendo ingredienti vietati.

    Tool READ-ONLY (rischio basso): non modifica nessuno stato esterno.

    Args:
        available_ingredients: ingredienti che l'utente ha a disposizione.
        dietary_constraints: solo tag positivi, es. ["vegetariano", "vegano"].
        excluded_ingredients: ingredienti vietati per allergie, intolleranze o avversioni.
        max_minutes: tempo massimo di preparazione in minuti.

    Returns:
        Lista di ricette compatibili che non contengono ingredienti esclusi.
    """
    candidates = _find_recipes(available_ingredients, dietary_constraints, max_minutes)
    excluded_set = set(i.lower() for i in excluded_ingredients)
    if not excluded_set:
        return candidates

    return [
        recipe
        for recipe in candidates
        if not any(ingredient.lower() in excluded_set for ingredient in recipe["ingredients"])
    ]


@tool(requires_confirmation=True)
def save_shopping_list(items: list[str]) -> str:
    """Salva la lista della spesa su file.

    Tool STATE UPDATE (rischio medio): richiede conferma esplicita.

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


class Constraints(BaseModel):
    """Vincoli alimentari normalizzati estratti dall'input dell'utente."""

    available_ingredients: list[str] = Field(default_factory=list)
    dietary_constraints: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    max_minutes: int = Field(default=60)


# endregion


def _recipe_recommendation_from_content(content: Any) -> RecipeRecommendation | None:
    """Normalizza l'output del Team prima della validazione business."""
    if isinstance(content, RecipeRecommendation):
        return content

    if isinstance(content, dict):
        data = content
    elif isinstance(content, str):
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OutputCheckError(
                f"Output RecipeRecommendation non parsabile come JSON: {exc}",
                check_trigger=CheckTrigger.OUTPUT_NOT_ALLOWED,
            ) from exc
    else:
        return None

    try:
        return RecipeRecommendation.model_validate(data)
    except Exception as exc:
        raise OutputCheckError(
            f"Output RecipeRecommendation non valido: {exc}",
            check_trigger=CheckTrigger.OUTPUT_NOT_ALLOWED,
        ) from exc


def validate_recipe_quality(run_output: TeamRunOutput) -> None:
    """Post-hook custom: verifica plausibilita' della ricetta proposta."""
    content = _recipe_recommendation_from_content(run_output.content)

    if not isinstance(content, RecipeRecommendation):
        return

    if not content.selected_recipe or len(content.selected_recipe.strip()) < 3:
        raise OutputCheckError(
            f"Nome ricetta non valido: {content.selected_recipe!r}.",
            check_trigger=CheckTrigger.OUTPUT_NOT_ALLOWED,
        )

    if (
        content.estimated_minutes is None
        or content.estimated_minutes <= 0
        or content.estimated_minutes > 240
    ):
        raise OutputCheckError(
            f"Tempo non plausibile: {content.estimated_minutes} minuti.",
            check_trigger=CheckTrigger.OUTPUT_NOT_ALLOWED,
        )

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

# === NUOVO: Workflow a 3 step ============================================

constraint_extractor = Agent(
    name="ConstraintExtractor",
    description="Estrae vincoli alimentari strutturati dal messaggio dell'utente.",
    model=Gemini(id="gemini-2.5-flash"),
    instructions=[
        "Sei un estrattore di vincoli alimentari.",
        "REGOLE:",
        "- excluded_ingredients: TUTTO cio' che l'utente non vuole (allergie, intolleranze, avversioni).",
        "- dietary_constraints: solo tag positivi: vegetariano, vegano, senza-glutine.",
        "ESEMPI:",
        "- 'allergica alle noci' -> excluded_ingredients=['noci'].",
        "- 'sono vegano' -> dietary_constraints=['vegetariano', 'vegano'].",
        "Quando in dubbio, includi nelle esclusioni: meglio scartare una ricetta valida che proporne una pericolosa.",
    ],
    output_schema=Constraints,
    use_json_mode=True,
)


def search_recipes_step(step_input: StepInput) -> StepOutput:
    """Step deterministico: query al RECIPES_DB."""
    constraints: Constraints = step_input.previous_step_content
    candidates = _find_recipes(
        available_ingredients=constraints.available_ingredients,
        dietary_constraints=constraints.dietary_constraints,
        max_minutes=constraints.max_minutes,
    )
    return StepOutput(
        content={
            "candidates": candidates,
            "constraints": constraints.model_dump(),
        }
    )


def filter_and_format_step(step_input: StepInput) -> StepOutput:
    """Step deterministico: filtra esclusioni e formatta."""
    data = step_input.previous_step_content
    candidates = data["candidates"]
    excluded = set(i.lower() for i in data["constraints"]["excluded_ingredients"])

    safe = [
        r for r in candidates
        if not any(ing.lower() in excluded for ing in r["ingredients"])
    ]

    if not safe:
        return StepOutput(content=f"Nessuna ricetta soddisfa i vincoli (escluse {len(excluded)}).")

    chosen = safe[0]
    return StepOutput(
        content=(
            f"**Ricetta consigliata: {chosen['name']}**\n\n"
            f"- Ingredienti: {', '.join(chosen['ingredients'])}\n"
            f"- Tempo: {chosen['minutes']} minuti\n"
            f"- Esclusioni applicate: {', '.join(sorted(excluded)) or 'nessuna'}"
        )
    )


recipe_workflow = Workflow(
    name="RecipeWorkflow",
    description="Pipeline a 3 step: estrai vincoli, cerca, filtra esclusioni.",
    db=db,
    steps=[
        Step(name="extract_constraints", agent=constraint_extractor),
        Step(name="search_recipes", executor=search_recipes_step),
        Step(name="filter_and_format", executor=filter_and_format_step),
    ],
)

recipe_worker = Agent(
    name="RecipeWorker",
    role="Cerca ricette compatibili con i vincoli dell'utente, usando reasoning e tool.",
    model=Gemini(id="gemini-2.5-flash"),
    instructions=[
        "Sei un assistente di cucina specializzato nella ricerca di ricette.",
        "Per ogni richiesta:",
        "1. Identifica vincoli (allergie, diete, tempo) e ingredienti disponibili.",
        "2. Usa find_safe_recipes_by_constraints quando l'utente indica allergie, intolleranze o ingredienti esclusi.",
        "3. Metti allergie ed esclusioni in excluded_ingredients, mai in dietary_constraints.",
        "4. dietary_constraints contiene solo tag positivi: vegetariano, vegano, senza-glutine.",
        "5. Usa find_recipes_by_constraints solo quando non ci sono esclusioni.",
        "6. Usa il reasoning per scegliere la migliore tra quelle compatibili.",
        "7. Restituisci una descrizione testuale della ricetta scelta:",
        "   - Nome della ricetta",
        "   - Tempo di preparazione",
        "   - Ingredienti mancanti",
        "   - Avvisi e motivazione",
        "Non produrre JSON: il leader del team lo fara' partendo dal tuo testo.",
    ],
    tools=[
        ReasoningTools(add_instructions=True),
        find_recipes_by_constraints,
        find_safe_recipes_by_constraints,
    ],
    reasoning_min_steps=1,
    reasoning_max_steps=4,
)


quality_eval = AgentAsJudgeEval(
    db=db,
    name="Recipe Quality Monitor",
    model=Gemini(id="gemini-2.5-flash"),
    criteria=(
        "La risposta deve essere coerente con i vincoli dell'utente. "
        "(1) Se l'utente ha dichiarato un'allergia, la ricetta NON deve "
        "contenere quell'ingrediente. "
        "(2) Se l'utente ha indicato un tempo massimo, deve essere "
        "rispettato. "
        "(3) La ricetta proposta deve essere realistica e fattibile."
    ),
    scoring_strategy="numeric",
    threshold=7,
    additional_guidelines=[
        "Penalizzare severamente la presenza di allergeni dichiarati.",
        "Penalizzare se il tempo proposto supera quello richiesto.",
    ],
    run_in_background=True,
    telemetry=False,
)


recipe_team = Team(
    name="RecipeTeam",
    description="Team che separa lavoro (worker con tool+reasoning) da formattazione (leader con schema).",
    mode=TeamMode.coordinate,
    model=Gemini(id="gemini-2.5-flash"),
    members=[recipe_worker],
    instructions=[
        "Sei il leader di un team che propone ricette all'utente.",
        "Per ogni richiesta:",
        "1. Delega al RecipeWorker per trovare la ricetta giusta.",
        "2. Se l'utente menziona allergie o ingredienti vietati, esplicita nella delega che sono esclusioni hard.",
        "3. Riceverai una descrizione testuale dal RecipeWorker.",
        "4. Estrai dalla sua risposta i campi dello schema RecipeRecommendation.",
        "5. Non aggiungere informazioni che il worker non ha fornito.",
        "6. Non chiamare tool: il worker ha gia' fatto il lavoro pesante.",
    ],
    output_schema=RecipeRecommendation,
    use_json_mode=True,
    show_members_responses=True,
    db=db,
    pre_hooks=[
        PromptInjectionGuardrail(injection_patterns=PROMPT_INJECTION_PATTERNS),
    ],
    post_hooks=[
        validate_recipe_quality,
        quality_eval,
    ],
)

agent_os = AgentOS(
    name="RecipeBot OS",
    agents=[recipebot],
    teams=[recipe_team],
    workflows=[recipe_workflow],
    db=db,
    tracing=True,
)

app = agent_os.get_app()
