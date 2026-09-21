"""
SIMULAZIONE PANDEMIA — un cittadino Agno (Gemini), il resto a regole.

  python -m pandemic_sim.main --scenario baseline --no-gif
  python -m pandemic_sim.main --scenario outbreak

Asia Deiana 20057114
Andrea Meda 20054214
"""
from dotenv import load_dotenv

load_dotenv()

import argparse
import random

from . import config
from .model import PandemicModel
from .scenarios import apply_scenario, list_scenarios
from .visualization import animate_simulation, plot_llm_behavior, plot_results


def main():
    # Applica lo scenario, gira la citta' giorno per giorno, poi grafici/GIF
    # sulla stessa corsa (niente chiamate Gemini extra per l'animazione).
    parser = argparse.ArgumentParser(description="Simulazione pandemia con un cittadino intelligente.")
    parser.add_argument("--scenario", default="baseline", choices=sorted(list_scenarios()))
    parser.add_argument("--no-gif", action="store_true", help="Salta l'animazione.")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed per rendere la corsa riproducibile (debug). Se omesso, ad ogni run viene scelto un seed casuale.",
    )
    args = parser.parse_args()

    description = apply_scenario(args.scenario)

    #Seed casuale ad ogni run (a meno che l'utente non ne passi uno esplicito con --seed):
    #cosi' contagi, percorsi dei bot e situazioni viste dal cittadino LLM cambiano di corsa in corsa.
    seed = args.seed if args.seed is not None else random.randrange(2**31)
    random.seed(seed)
    print(f"Seed: {seed}" + (" (fisso, passato con --seed)" if args.seed is not None else " (casuale)"))
    print(f"Scenario: {args.scenario} — {description}")
    print(f"giorni={config.N_DAYS}  agenti={config.N_AGENTS}")

    full_model = PandemicModel()
    full_model.run(total_hours=config.N_DAYS * config.HOURS_PER_DAY)
    print(
        f"Finale -> S:{full_model.history['S'][-1]} E:{full_model.history['E'][-1]} "
        f"I:{full_model.history['I'][-1]} R:{full_model.history['R'][-1]} "
        f"Morti:{full_model.history['D'][-1]} "
        f"Vaccinati:{full_model.vaccinated_history[-1]} "
        f"lockdown F{full_model.lockdown_phase} "
        f"chiamate Gemini: {full_model.llm_call_count}"
    )
    plot_results(full_model)
    plot_llm_behavior(full_model)

    if not args.no_gif:
        print("Genero l'animazione della stessa corsa (niente chiamate extra)...")
        animate_simulation(full_model)


if __name__ == "__main__":
    main()