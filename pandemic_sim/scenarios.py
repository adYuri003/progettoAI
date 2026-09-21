# Due mondi: stessa citta' e stessi agenti, numeri diversi.
# baseline = corsa normale; outbreak = focolaio alto, fasi che arrivano prima.

from . import config
from .poi import BAR, HOSPITAL, MALL, PARCO, VACCINE_CENTER

SCENARIOS = {
    "baseline": {   #virus base 
        "description": "Epidemia che parte lenta; lockdown a soglie di infetti, vaccini in fase 3.",
        "params": {
            "N_DAYS": 15,    #giorni di simulazione
            "INITIAL_INFECTED": 3,   #persone inizialente contagiate
            "INFECTION_PROB_PRE": config.INFECTION_PROB_PRE,   #probabilità di infettarsi pre lockdown
            "INFECTION_PROB_LOCKDOWN": config.INFECTION_PROB_LOCKDOWN,   #probabilità di infettarsi durante lockdown
            "LOCKDOWN_PHASE1_INFECTED": config.LOCKDOWN_PHASE1_INFECTED,  #soglia per fase 1
            "LOCKDOWN_PHASE2_INFECTED": config.LOCKDOWN_PHASE2_INFECTED,
            "LOCKDOWN_PHASE3_INFECTED": config.LOCKDOWN_PHASE3_INFECTED,
            "HOSPITAL_CAPACITY": config.HOSPITAL_CAPACITY,   #capacità ospedale
            "LETHAL_OUTBREAK": False,   
        },
    },
    "outbreak": {    #epidemia più cattiva 
        "description": "Focolaio iniziale alto. Il cittadino dovrebbe chiudersi appena scatta il lockdown.",
        "params": {
            "N_DAYS": 15,
            "INITIAL_INFECTED": 17,
            "INFECTION_PROB_PRE":config.INFECTION_PROB_PRE*1.5,
            "INFECTION_PROB_LOCKDOWN": config.INFECTION_PROB_LOCKDOWN*1.5,
            "LOCKDOWN_PHASE1_INFECTED": config.LOCKDOWN_PHASE1_INFECTED,
            "LOCKDOWN_PHASE2_INFECTED": config.LOCKDOWN_PHASE2_INFECTED,
            "LOCKDOWN_PHASE3_INFECTED": config.LOCKDOWN_PHASE3_INFECTED,
            "HOSPITAL_CAPACITY": round(config.HOSPITAL_CAPACITY),
            "LETHAL_OUTBREAK": False,  #il virus non può uccidere
        },
    },
    "lethal": {   #virus aggressivo (simulatore di virus letali, es. peste)
        "description": "Virus letale",
        "params": {
            "N_DAYS": 15,  
            "INITIAL_INFECTED": 20,
            "INFECTION_PROB_PRE": 0.60,
            "INFECTION_PROB_LOCKDOWN": 0.45,
            "LOCKDOWN_PHASE1_INFECTED": config.LOCKDOWN_PHASE1_INFECTED,
            "LOCKDOWN_PHASE2_INFECTED": config.LOCKDOWN_PHASE2_INFECTED,
            "LOCKDOWN_PHASE3_INFECTED": config.LOCKDOWN_PHASE3_INFECTED,
            "HOSPITAL_CAPACITY": round(config.HOSPITAL_CAPACITY),
            "LETHAL_OUTBREAK": True,
        },
    },
}

#funzione di attivazione dello scenario scelto 
def apply_scenario(name: str) -> str:
    if name not in SCENARIOS:
        known = ", ".join(SCENARIOS)
        raise ValueError(f"Scenario sconosciuto: {name!r}. Disponibili: {known}")

    spec = SCENARIOS[name]
    for key, value in spec["params"].items():
        setattr(config, key, value)   #applica i valori dello scenario (li salva nell'oggetto config)

    # All'avvio siamo sempre in fase 0: virus cattivo, vaccini ancora invisibili.
    config.INFECTION_PROB = config.INFECTION_PROB_PRE
    config.ILLNESS_HOURS = config.ILLNESS_HOURS_PRE
    config.VACCINE_START_DAY = 10**9
    config.CURFEW_HOUR = 23
    HOSPITAL.capacity = config.HOSPITAL_CAPACITY
    VACCINE_CENTER.open_from_day = config.VACCINE_START_DAY
    BAR.open_from_day = 0
    BAR.open_hour, BAR.close_hour = 18, 23
    PARCO.open_from_day = 0
    MALL.open_hour, MALL.close_hour = 9, 20
    config.ACTIVE_SCENARIO = name
    return spec["description"]


#restituisce un elenco di tutti gli scenari disponibili e le loro caratteristiche 
def list_scenarios() -> dict[str, str]:
    return {name: spec["description"] for name, spec in SCENARIOS.items()}
