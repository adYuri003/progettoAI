# Tool di sola lettura sullo stato della citta' e del cittadino osservato.
from agno.tools import tool

from . import config
from .poi import BAR, HOSPITAL, MALL, PARCO, VACCINE_CENTER

#variabili globali, impostate ad ogni chiamata a Gemini e letti dai tool quando vengono invocati 
_current_model = None
_current_citizen = None

#set_active_world viene chiamato prima di ogni tool per impostare il contesto della citta' e del cittadino osservato. Non modifica lo stato della simulazione, ma comunica all'agente LLM lo stato della citta' e del cittadino osservato.
#Agente LLM puo' usare questi dati per prendere decisioni sulla policy, ma non puo' modificare lo stato della simulazione direttamente 
#Se il model non e' disponibile (perche la simulazione e' terminata) i tool restituiscono un messaggio di errore.

#Funzione di utilita' per l'agente LLM (solo lettura, non modifica lo stato della simulazione ma comunica all'agente lo stato della citta')
#questa funzione aggiorna le variabili globali con il riferimento al modello di simulazione e al
#cittadino che si stanno utilizzando ora
def set_active_world(model, citizen=None):
    global _current_model, _current_citizen
    _current_model = model
    _current_citizen = citizen

#Funzione che legge lo stato della citta con un controllo di sicurezza, utilizzato in altre funzioni per controllare che il model sia disponibile prima di accedere ai dati della citta
#è una funzione di controllo per verificare che il model sia stato impostato
def _require_world():
    if _current_model is None:
        return None
    return _current_model

#Funzione che costruisce un dizionario con lo snapshot dello stato della citta' 
# e del cittadino osservato (raccoglie tutti i dati che dovranno essere inviati a Gemini)
def build_snapshot(model, citizen, day: int, hour: int = 0) -> dict:
    #per ogni agente (a) con stato infetto I, produce n numero (1). Sommando tutti gli 1 con sum()
    # si ottiene il numero degli infetti 
    infected = sum(1 for a in model.agents if a.state == config.I)  
    total = max(1, len(model.agents))   #recupera il numero complessivo di cittadini
    vaccine_open = VACCINE_CENTER.is_open(max(hour, 8), day)  #controllo apertura centro vaccinale
    hospital_full = not HOSPITAL.has_room()  #controllo ospedale pieno
    return {
        "day": day,
        "hour": hour,
        "scenario": config.ACTIVE_SCENARIO,
        "lockdown_phase": getattr(model, "lockdown_phase", 0),
        "citizen_id": citizen.id,
        "age": getattr(citizen, "age", None),
        "personality": citizen.personality,
        "schedule_offset": getattr(citizen, "schedule_offset", 0),
        "health": config.perceived_state(citizen.state),
        "vaccinated": citizen.vaccinated,
        "novax": citizen.novax,
        "severe": citizen.severe,
        "hospitalized": citizen.hospitalized,
        "infected_count": infected,
        "population": total,
        "infection_rate": infected / total,
        "hospital_occupants": len(HOSPITAL.occupants),
        "hospital_capacity": HOSPITAL.capacity,
        "hospital_full": hospital_full,
        "vaccine_open": vaccine_open,
        "curfew_hour": config.CURFEW_HOUR,
        "bar_open": BAR.is_open(hour if hour else 19, day),
        "mall_open": MALL.is_open(hour if hour else 12, day),
        "park_open": PARCO.is_open(hour if hour else 12, day),
        "yesterday": getattr(citizen, "yesterday_note", "nessuna nota"),
    }

#I tool trasformano una normale funzione in un qualcosa che il modello LLM puo vedere e 
#decidere di chiamare da solo
#Tool di sola lettura per l'agente LLM, esponde i dati anagrafici e sanitari del cittadino 
@tool   #serve a specificare che non stiamo indicando solo una funzione, ma qualcosa che LLM può chiamare liberamente
def get_personal_status() -> str:
    #testo che Agno invia a Gemini er descrivere a cosa serve questo tool
    """Stato di salute, eta', vaccino e personalita' del cittadino osservato."""
    model = _require_world()    #verifico che il modello esista 
    if model is None or _current_citizen is None:
        return "Cittadino non disponibile."
    c = _current_citizen

    #Ritorno una stringa con i dati del cittadino osservato, che l'agente LLM 
    # puo usare per prendere decisioni sulla policy
    return (
        f"id={c.id} eta={c.age} ruolo={c.role} personalita={c.personality} "
        f"salute={config.perceived_state(c.state)} grave={c.severe} ospedalizzato={c.hospitalized} "
        f"vaccinato={c.vaccinated}"
    )  #restituisco una stringa che verrà passata a Gemini
    #perceived_state applica il filtro (stato E--> stato S percepito)

#Tool di sola lettura che calcola la percentuale di infetti scorrendo la lista degli agenti 
# della citta' e contando quanti sono nello stato I (infetto) e quanti sono totali
@tool
def get_city_infection_rate() -> str:
    """Percentuale di popolazione attualmente infetta (stato I) e fase lockdown."""
    model = _require_world()
    if model is None:
        return "Dati citta' non disponibili."
    infected = sum(1 for a in model.agents if a.state == config.I)   #totale infetti
    total = len(model.agents)   #totale cittadini
    phase = getattr(model, "lockdown_phase", 0)   #recupero fase di lockdown (0 se non è definita)

    #Ritorna una stringa con il numero di infetti, il numero totale e la percentuale di infetti, 
    # insieme alla fase di lockdown attuale. (.1% per rappresentazione percentuale)
    return (
        f"{infected}/{total} infetti ({infected / total:.1%}); "
        f"lockdown fase {phase}"
    )

#Tool di sola lettura che utilizza HOSPITAL per calcolare l'occupazione e la capienza dell'ospedale 
@tool
def get_hospital_status() -> str:
    """Occupazione e capienza dell'ospedale."""

    #ritorna una stringa con il numero di posti occupati, la capienza totale e se l'ospedale e' 
    # saturo o ha posti liberi.
    return (
        f"Ospedale: {len(HOSPITAL.occupants)}/{HOSPITAL.capacity} posti. "
        f"{'SATURO' if not HOSPITAL.has_room() else 'posti liberi'}"
    )

#Tool di sola lettura che utilizza i POI per calcolare quali luoghi pubblici sono aperti oggi, 
# in base all'ora e al giorno corrente della simulazione. Il vaccino compare solo se attivo.
@tool
def get_open_places() -> str:
    """Quali luoghi pubblici sono aperti oggi. Il vaccino compare solo se attivo."""
    model = _require_world()
    day = model.day if model is not None else 0
    hour = model.hour if model is not None else 12
    places = []   #lista riempita progressivamente
    for poi in (BAR, MALL, PARCO, HOSPITAL):
        places.append(f"{poi.name}: {'aperto' if poi.is_open(hour, day) else 'chiuso'}")
    if VACCINE_CENTER.is_open(max(hour, 8), day):  #aggiunge alla lista il centro vaccinale se aperto
        places.append(f"{VACCINE_CENTER.name}: aperto")
    else:
        places.append("Centro vaccinale: non ancora visibile / chiuso")
    places.append(f"coprifuoco alle {config.CURFEW_HOUR}")
    if model is not None:
        places.append(f"lockdown fase {model.lockdown_phase}")
    return "; ".join(places)  #unisco tutti gli elementi nella lista con ; come separatore
#ottengo una stringa da passare a Gemini

#Tool di sola lettura che restituisce cosa e' successo al cittadino ieri 
# (contagio, ricovero, vaccino).
@tool
def get_yesterday_outcome() -> str:
    """Cosa e' successo al cittadino ieri (contagio, ricovero, vaccino)."""
    if _current_citizen is None:
        return "Nessuna memoria ieri."
    return getattr(_current_citizen, "yesterday_note", "Nessun evento particolare ieri.")
