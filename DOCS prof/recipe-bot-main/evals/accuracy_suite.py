from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Literal

from agno.eval.accuracy import AccuracyEval, AccuracyResult

from recipebot_evaluated import Gemini, db, recipe_team, recipebot


Target = Literal["agent", "team"]


@dataclass(frozen=True)
class GoldCase:
    title: str
    input: str
    expected_output: str
    additional_guidelines: list[str]


BASE_GUIDELINES = [
    "Valuta se la risposta rispetta i vincoli hard dell'utente.",
    "Penalizza severamente allergeni vietati, ricette inventate e tempi non rispettati.",
    "Una risposta che segnala correttamente l'impossibilita' di soddisfare i vincoli puo' essere accurata.",
]


GOLD_CASES = [
    GoldCase(
        title="01 - Allergia alle noci (bug #1)",
        input=(
            "Sono allergica alle noci. Ho ceci, zucchine, limone, pasta, "
            "rucola, parmigiano, olio. Cosa posso preparare in 30 minuti?"
        ),
        expected_output=(
            "Consiglia una ricetta senza noci e pronta in massimo 30 minuti, "
            "per esempio Insalata di ceci e zucchine. Non proporre Pasta al "
            "pesto di rucola perche contiene noci."
        ),
        additional_guidelines=[
            "Se la risposta propone noci o una ricetta che contiene noci, il punteggio massimo e' 4.",
            "Premia risposte che nominano esplicitamente il rischio allergene.",
        ],
    ),
    GoldCase(
        title="02 - Dieta vegana",
        input="Ho ceci, limone, tahini e aglio. Sono vegana e ho poco tempo.",
        expected_output=(
            "Consiglia Hummus express o una ricetta equivalente vegana, usando "
            "ceci, limone, tahini e aglio, con tempo intorno a 10 minuti."
        ),
        additional_guidelines=[
            "Penalizza ingredienti non vegani come parmigiano, yogurt o uova.",
            "Premia risposte che mantengono il vincolo vegano come hard constraint.",
        ],
    ),
    GoldCase(
        title="03 - Tempo stretto",
        input="Ho ceci, limone, tahini e aglio. Voglio qualcosa in massimo 10 minuti.",
        expected_output=(
            "Consiglia Hummus express o una ricetta equivalente pronta in massimo "
            "10 minuti con gli ingredienti indicati."
        ),
        additional_guidelines=[
            "Penalizza ricette oltre 10 minuti.",
            "Premia risposte che riportano chiaramente il tempo stimato.",
        ],
    ),
    GoldCase(
        title="04 - Vincoli incompatibili",
        input="Ho solo pasta. Voglio una ricetta vegana completa in 5 minuti.",
        expected_output=(
            "Non inventare una ricetta completa. Spiega che i vincoli sono troppo "
            "restrittivi con i soli ingredienti disponibili e chiedi di aggiungere "
            "ingredienti o allentare il vincolo di tempo."
        ),
        additional_guidelines=[
            "Premia il riconoscimento esplicito del conflitto tra ingredienti e vincoli.",
            "Penalizza ricette inventate o non realizzabili con gli ingredienti forniti.",
        ],
    ),
    GoldCase(
        title="05 - Out-of-scope (proxy bug #4)",
        input="Quanto fa 23 x 47?",
        expected_output=(
            "Non comportarsi come assistente generico. Rifiuta o reindirizza "
            "brevemente verso il dominio cucina/ricette."
        ),
        additional_guidelines=[
            "Se la risposta calcola 1081 senza reindirizzare al dominio RecipeBot, il punteggio massimo e' 4.",
            "Premia risposte brevi che mantengono il ruolo di assistente di cucina.",
        ],
    ),
]


def _score(result: AccuracyResult | None) -> float | None:
    if result is None or not result.results:
        return None
    return float(result.avg_score)


def _reason(result: AccuracyResult | None) -> str:
    if result is None or not result.results:
        return "Nessun risultato prodotto dall'evaluator."
    return result.results[0].reason


def _build_eval(case: GoldCase, target: Target) -> AccuracyEval:
    component_kwargs = {"agent": recipebot} if target == "agent" else {"team": recipe_team}
    component_name = "RecipeBot" if target == "agent" else "RecipeTeam"

    return AccuracyEval(
        name=f"{case.title} - {component_name}",
        input=case.input,
        expected_output=case.expected_output,
        model=Gemini(id="gemini-2.5-flash"),
        db=db,
        num_iterations=1,
        additional_guidelines=BASE_GUIDELINES + case.additional_guidelines,
        telemetry=False,
        **component_kwargs,
    )


def run_eval_for_case(case: GoldCase, target: Target) -> AccuracyResult | None:
    component_name = "RecipeBot" if target == "agent" else "RecipeTeam"
    print(f"\nCaso: {case.title}")
    print(f"Target: {'agent' if target == 'agent' else 'team'} = {component_name}")

    evaluation = _build_eval(case, target)
    try:
        result = evaluation.run(print_summary=False, print_results=False)
    except Exception as exc:
        print(f"Run target fallita: {type(exc).__name__}: {exc}")
        print("Valuto l'errore come output del sistema, cosi' la suite resta eseguibile.")
        result = evaluation.run_with_output(
            output=f"ERROR: {type(exc).__name__}: {exc}",
            print_summary=False,
            print_results=False,
        )

    score = _score(result)
    print(f"Score: {score:.1f}/10" if score is not None else "Score: n/a")
    print(f"Reason: {_reason(result)}")
    return result


def run_single_case(index: int) -> None:
    case = GOLD_CASES[index]
    agent_result = run_eval_for_case(case, "agent")
    team_result = run_eval_for_case(case, "team")

    agent_score = _score(agent_result)
    team_score = _score(team_result)

    print("\n" + "-" * 48)
    print(f"Confronto su: {case.title}")
    print(f"  v1 (agente):     {agent_score:.1f}/10" if agent_score is not None else "  v1 (agente):     n/a")
    print(
        f"  Team governato:  {team_score:.1f}/10"
        if team_score is not None
        else "  Team governato:  n/a"
    )
    if agent_score is not None and team_score is not None:
        print(f"  Differenza:      {team_score - agent_score:+.1f}")
    print("-" * 48)
    print("Risultato salvato in tmp/recipebot.db.")
    print("Visibile nel Control Plane -> pagina Evaluations.")


def run_all_cases() -> None:
    for index in range(len(GOLD_CASES)):
        run_single_case(index)


def main() -> None:
    parser = argparse.ArgumentParser(description="Suite gold AccuracyEval per RecipeBot.")
    parser.add_argument("--single", type=int, help="Indice del caso da eseguire, 0-based.")
    args = parser.parse_args()

    if args.single is None:
        run_all_cases()
        return

    if args.single < 0 or args.single >= len(GOLD_CASES):
        raise SystemExit(f"Indice non valido: {args.single}. Valori ammessi: 0-{len(GOLD_CASES) - 1}.")

    run_single_case(args.single)


if __name__ == "__main__":
    main()
