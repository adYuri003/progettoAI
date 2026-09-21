# Grafici e animazione della simulazione pandemica.

import bisect

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
import bisect
import textwrap #Per spezzare le stringhe di testo troppo lunghe in più righe per l'annotazione

from . import config
from .city import CITY_MAP, GRID_W, GRID_H
from .poi import HOSPITAL, VACCINE_CENTER, BAR, MALL, PARCO

#Colore acceso riservato al cittadino osservato (LLM), per distinguerlo a colpo d'occhio dai bot.
#CITIZEN_COLOR = "#FF00FF"  # magenta
CITIZEN_MARKER_SIZE = 70
DEFAULT_MARKER_SIZE = 20

REASON_WRAP_WIDTH = 62   # caratteri per riga prima di andare a capo
REASON_MAX_LINES = 7     # righe totali massime

#Etichette in italiano per lo stato di salute, mostrate sotto il grafico dell'animazione.
STATE_LABELS_IT = {
    config.S: "Sano",
    config.E: "Asintomatico",
    config.I: "Malato",
    config.R: "Guarito",
    config.D: "Deceduto",
}

#Estrae, dallo storico delle policy del cittadino, solo le decisioni effettivamente
#prese chiamando Gemini (esclude i giorni in cui e' stata riusata la cache), ordinate per giorno.
def _build_llm_events(model):
    records = model.llm_policy_history.get(config.LLM_CITIZEN_ID, [])
    events = [r for r in records if r.get("used_llm")]
    events.sort(key=lambda r: r["day"])
    return events

#Trova l'ultima decisione Gemini attiva in un dato giorno (quella rimane valida finche' non
#ne arriva una nuova, coerente con la cache riusata dalla simulazione).
def _active_llm_event(events, day):
    if not events:
        return None
    days = [e["day"] for e in events]
    idx = bisect.bisect_right(days, day) - 1
    if idx < 0:
        return None
    return events[idx]

def plot_results(model, filename="epidemic_curve_advanced.png"):
    hours = np.arange(len(model.history[config.S]))
    days = hours / config.HOURS_PER_DAY

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    ax.plot(days, model.history[config.S], label="Susceptible", color="steelblue")
    ax.plot(days, model.history[config.E], label="Asintomatic", color="orange")
    ax.plot(days, model.history[config.I], label="Infected", color="crimson")
    ax.plot(days, model.history[config.R], label="Recovered", color="seagreen")
    ax.plot(days, model.history[config.D], label="Deceduti", color="black", linestyle="--")
    for ev in getattr(model, "lockdown_events", []):
        ax.axvline(ev["day"], color="gray", linestyle="--", alpha=0.7)
        ax.text(ev["day"], ax.get_ylim()[1] * 0.95 if ax.get_ylim()[1] else 1,
                f"F{ev['phase']}", fontsize=8, color="gray")
    if model.vaccine_opened_on_day is not None:
        ax.axvline(model.vaccine_opened_on_day, color="purple", linestyle=":", label="Apertura vaccini")
    ax.set_xlabel("Giorni")
    ax.set_ylabel("Numero di agenti")
    ax.set_title(f"Curva epidemica ({config.ACTIVE_SCENARIO})")
    ax.legend(fontsize=8)

    ax2 = axes[1]
    ax2.plot(days, model.hospital_history, color="firebrick", label="Occupazione ospedale")
    ax2.axhline(HOSPITAL.capacity, color="black", linestyle="--", label="Capienza max")
    ax2.plot(days, model.vaccinated_history, color="purple", label="Vaccinati (cumulato)")
    ax2.set_xlabel("Giorni")
    ax2.set_title("Ospedale e campagna vaccinale")
    ax2.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    print(f"Grafico salvato in {filename}")


def build_city_background(vaccine_visible=False):
    grid = np.zeros((GRID_H, GRID_W, 3))

    colors = {
        ".": (0.25, 0.25, 0.25),
        "#": (0.72, 0.53, 0.35),
        "c": (0.5, 0.5, 0.8),
        "h": (0.8, 0.5, 0.5),
        "p": (0.5, 0.8, 0.5),
        "b": (0.8, 0.8, 0.5),
        "v": (0.75, 0.55, 0.85) if vaccine_visible else (0.25, 0.25, 0.25),
    }
    wall = (0.85, 0.85, 0.85)

    for x in range(GRID_W):
        for y in range(GRID_H):
            ch = CITY_MAP[y][x]
            grid[y, x] = colors.get(ch, wall)
    return grid


def poi_rectangle(poi, **kwargs):
    x0 = poi.min_x - 0.5
    y0 = poi.min_y - 0.5
    width = (poi.max_x - poi.min_x) + 1
    height = (poi.max_y - poi.min_y) + 1
    return mpatches.Rectangle((x0, y0), width, height, **kwargs)


def animate_simulation(model, filename="simulation_advanced.gif"):
    #Rigioca la corsa gia' eseguita: nessuna nuova decisione Gemini.
    frames_data = model.frame_history
    if not frames_data:
        print("Nessun frame da animare.")
        return model

    color_map = {
        config.S: "steelblue",
        config.E: "orange",
        config.I: "crimson",
        config.R: "seagreen",
        config.D: "black",
    }

    llm_events = _build_llm_events(model)

    fig, ax = plt.subplots(figsize=(7, 8.6))
    fig.subplots_adjust(bottom=0.16, top=0.88)
    bg_hidden = build_city_background(vaccine_visible=False)
    bg_shown = build_city_background(vaccine_visible=True)
    img = ax.imshow(bg_hidden, origin="lower", extent=(-0.5, GRID_W - 0.5, -0.5, GRID_H - 0.5))

    scat = ax.scatter([], [], s=DEFAULT_MARKER_SIZE, zorder=3, linewidths=1.2)
    citizen_scat = ax.scatter([], [], s=CITIZEN_MARKER_SIZE, zorder=4, linewidths=2.0, edgecolors="gold")

    #Contatore infetti
    infected_text = fig.text(
        0.99, 0.600, "", ha="right", va="top",
        fontsize=9, weight="bold", color="white", zorder=5,
        bbox=dict(boxstyle="round", facecolor="crimson", alpha=0.85, edgecolor="none"),
    )

    #Conteggio dei deceduti
    deaths_text = fig.text(
        0.01, 0.600, "", ha="left", va="top",
        fontsize=9, weight="bold", color="white", zorder=5,
        bbox=dict(boxstyle="round", facecolor="black", alpha=0.75, edgecolor="none"),
    )

    #Stato di salute del cittadino osservato
    state_text = fig.text(0.5, 0.27, "", ha="center", va="top", fontsize=12, weight="bold")
    
    #Spiegazione (2 righe) dell'ultima decisione di Gemini: avvicinata di conseguenza.
    reason_text = fig.text(
        0.5, 0.235, "", ha="center", va="top", fontsize=8.5, color="#333333", linespacing=1.4
    )

    hospital_patch = poi_rectangle(HOSPITAL, fill=False, edgecolor="black", linewidth=1.5, zorder=2)
    ax.add_patch(hospital_patch)

    vaccine_patch = poi_rectangle(
        VACCINE_CENTER, facecolor="purple", alpha=0.3, edgecolor="purple", linewidth=1.5, zorder=2
    )
    vaccine_patch.set_visible(False)
    ax.add_patch(vaccine_patch)

    #Etichette POI: bar e parco sotto, mall e ospedale sopra.
    LABELS_BELOW = {BAR, PARCO}
    labels = {}
    for poi in (BAR, MALL, PARCO, HOSPITAL):
        half_height = (poi.max_y - poi.min_y) / 2
        if poi in LABELS_BELOW:
            label_y = poi.pos[1] - half_height - 1.2
        else:
            label_y = poi.pos[1] + half_height + 1.2
        labels[poi.name] = ax.annotate(
            poi.name,
            (poi.pos[0], label_y),
            fontsize=8,
            ha="center",
        )
    vaccine_label = ax.annotate(
        VACCINE_CENTER.name,
        (VACCINE_CENTER.pos[0], VACCINE_CENTER.pos[1] + (VACCINE_CENTER.max_y - VACCINE_CENTER.min_y) / 2 + 1.2),
        fontsize=7,
        ha="center",
    )
    vaccine_label.set_visible(False)

    hospital_label = ax.text(
        HOSPITAL.pos[0], HOSPITAL.pos[1], "", fontsize=8, ha="center", va="center", zorder=4, weight="bold"
    )

    ax.set_xlim(-1, GRID_W)
    ax.set_ylim(-1, GRID_H)
    title = ax.set_title("Simulazione citta' - giorno 0, ora 0")

    def update(frame):
        rec = frames_data[frame]
        states = rec["states"]
        is_citizen_flags = rec["is_citizen"]
        citizen_idx = is_citizen_flags.index(True) if True in is_citizen_flags else None

        # --- Bot: tutti tranne Truman, in un unico scatter ---
        bot_indices = [i for i in range(len(states)) if i != citizen_idx]
        bot_xs = [rec["xs"][i] for i in bot_indices]
        bot_ys = [rec["ys"][i] for i in bot_indices]
        bot_colors = [color_map[states[i]] for i in bot_indices]

        scat.set_offsets(np.c_[bot_xs, bot_ys])
        scat.set_color(bot_colors)
        scat.set_sizes([DEFAULT_MARKER_SIZE] * len(bot_indices))
        scat.set_edgecolor("none")

        # --- Truman: scatter separato, sempre sopra grazie allo zorder piu' alto ---
        if citizen_idx is not None:
            c_state = states[citizen_idx]
            c_color = color_map[c_state]
            citizen_scat.set_offsets(np.c_[[rec["xs"][citizen_idx]], [rec["ys"][citizen_idx]]])
            citizen_scat.set_facecolor(c_color)

        # Infetti e deceduti
        infected_now = states.count(config.I)
        deaths_now = states.count(config.D)
        total_agents = len(states)
        infected_text.set_text(f"Infetti: {infected_now}/{total_agents}")
        deaths_text.set_text(f"Deceduti: {deaths_now}")

        # Stato di salute del cittadino osservato
        citizen_state = rec.get("citizen_state")
        state_label = STATE_LABELS_IT.get(citizen_state, citizen_state or "?")
        state_text.set_text(f"Truman: {state_label}")

        # Ultima decisione presa da Gemini (non la cache), resta finche' non ne arriva una nuova
        event = _active_llm_event(llm_events, rec["day"])
        if event:
            line1 = (
                f"Decisione Gemini (giorno {event['day']}, F{event.get('lockdown_phase', '?')}): "
                f"destinazione={event.get('intended_place', '?')}  "
                f"socievolezza={event.get('sociability', 0):.2f}  "
                f"rischio={event.get('risk_tolerance', 0):.2f}"
            )
            reason_raw = (event.get("reason") or "").strip()

            wrapped_line1 = textwrap.wrap(line1, width=REASON_WRAP_WIDTH) or [""]
            remaining_lines = max(1, REASON_MAX_LINES - len(wrapped_line1))
            wrapped_reason = textwrap.wrap(reason_raw, width=REASON_WRAP_WIDTH)
            if len(wrapped_reason) > remaining_lines:
                wrapped_reason = wrapped_reason[:remaining_lines]
                wrapped_reason[-1] = wrapped_reason[-1].rstrip() + "..."

            reason_text.set_text("\n".join(wrapped_line1 + wrapped_reason))
        else:
            reason_text.set_text("Nessuna decisione di Gemini ancora presa (routine iniziale).")

        ratio = rec["hospital_occupants"] / max(1, HOSPITAL.capacity)
        hospital_patch.set_facecolor((min(1, ratio * 2), min(1, (1 - ratio) * 2), 0))
        hospital_patch.set_fill(True)
        hospital_patch.set_alpha(0.45)
        hospital_label.set_text(f"{rec['hospital_occupants']}/{HOSPITAL.capacity}")

        show_vax = rec.get("vaccine_active", False)
        img.set_data(bg_shown if show_vax else bg_hidden)
        vaccine_patch.set_visible(show_vax)
        vaccine_label.set_visible(show_vax)
        phase = rec.get("lockdown_phase", 0)
        title.set_text(f"Simulazione citta' - giorno {rec['day']}, ora {rec['hour']}, lockdown F{phase}")
    return scat, citizen_scat 

    ani = animation.FuncAnimation(fig, update, frames=len(frames_data), interval=100, blit=False)
    ani.save(filename, writer="pillow", fps=4)
    print(f"Animazione salvata in {filename}")
    plt.close(fig)
    return model


def plot_llm_behavior(model, filename="llm_agents_behavior.png"):
    if not model.llm_policy_history:
        print("Nessun dato di comportamento del cittadino da visualizzare.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    records = next(iter(model.llm_policy_history.values()))
    days = [r["day"] for r in records]
    axes[0].plot(days, [r["sociability"] for r in records], marker="o", color="gold")
    axes[0].set_title("Truman: socievolezza")
    axes[0].set_xlabel("Giorno")
    axes[0].set_ylabel("Sociability today")
    axes[0].set_ylim(0, 1)

    axes[1].plot(days, [r["risk_tolerance"] for r in records], marker="o", color="crimson")
    axes[1].set_title("Cittadino osservato: tolleranza al rischio")
    axes[1].set_xlabel("Giorno")
    axes[1].set_ylabel("Risk tolerance")
    axes[1].set_ylim(0, 1)

    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    print(f"Grafico comportamento cittadino salvato in {filename}")
    print("Decisioni giornaliere:")
    for r in records:
        print(
            f"  g{r['day']} F{r.get('lockdown_phase', '?')}: place={r.get('intended_place')} "
            f"soc={r['sociability']:.2f} risk={r['risk_tolerance']:.2f} "
            f"vax={r['wants_vaccine']} llm={r.get('used_llm')} | {r.get('reason', '')[:80]}"
        )