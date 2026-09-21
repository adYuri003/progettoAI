# Percorsi e attivita' fisse dei bot. Stesso codice per tutti, timer interno
# sfasato per gruppo cosi' non finiscono tutti al supermercato lo stesso giorno.
# Una sola attivita' diurna; qualche uscita serale scelta a caso in init.

from . import config
from .poi import BAR, MALL, PARCO, VACCINE_CENTER


def grocery_interval(phase, role):    #intervallo di giorni per spesa in base alla fase di lockdown 
    # I no-vax ignorano il ritmo da lockdown e restano sul ciclo da 5 giorni.
    if role == "novax":
        return config.GROCERY_INTERVAL_BY_PHASE[0]   #i novax seguono sempre i ritmi pre lockdown
    #gli altri cittadini seguono l'intervallo della fase attuale (altrimenti un default di 5 giorni)
    return config.GROCERY_INTERVAL_BY_PHASE.get(phase, 5)


def is_grocery_day(agent, day, phase):   #divide gli intervalli dei grupi di agenti 
    interval = grocery_interval(phase, agent.role)
    return ((day + agent.schedule_offset) % interval) == 0
#in questo modo, non tutti faranno la spesa lo stesso giorno 


def is_park_day(agent, day, phase):    #giornata per andare al parco
    if phase == 1 and agent.role != "novax":   #si controlla di non essere in fase 1 e novax
        return False
    return ((day + agent.schedule_offset) % 7) == 3
#si sfasano ancora gli agenti in base al gruppo


def night_out_allowed(agent, phase):   #uscire di sera
    if agent.role == "novax":    #se l'agente è novax, esce di sera comunque 
        return True
    return phase in (0, 1)   #uscita permessa solo nella fase 0 e 1
#in queste due fasi, l'uscita notturna è permessa anche se regolata da un coprifuoco
#nelle fasi successive, l'uscita sarà comunque regolata da coprifuoco ma fortemente scoraggiata 


def is_vaccine_day(agent, day, phase):
    # Solo i bot (non no-vax) hanno questo codice extra dalla fase 3.
    if phase < 3 or agent.novax or agent.vaccinated or agent.state == config.I:
        return False
    return ((day + agent.schedule_offset) % 4) == 1
#si usa ancora uno sfasamento per i bot, evitando che si vaccinino in gruppi troppo numerosi

#definizione degli obiettivi degli agenti
def plan_day(agent, day, phase):
    if is_vaccine_day(agent, day, phase):
        agent.today_activity = "vaccine"
    elif is_grocery_day(agent, day, phase):
        agent.today_activity = "grocery"
    elif is_park_day(agent, day, phase):
        agent.today_activity = "park"
    else:
        agent.today_activity = "home"

    modulo = config.NIGHT_OUT_MODULO_NOVAX if agent.role == "novax" else config.NIGHT_OUT_MODULO
    agent.night_out_tonight = (
        night_out_allowed(agent, phase)
        and ((day + agent.night_seed) % modulo == 0)
        #le usite serali sono sfasate individualmente (tramite un parametro individuale scelto 
        #casualmente per ogni agente: agent.night_seed)
    )


def scripted_place(agent, hour, day, phase):
    if not getattr(agent, "day_activity_done", False):  #se l'attività della giornata non è ancora stata completata
        if agent.today_activity == "vaccine" and VACCINE_CENTER.is_open(hour, day):
            return VACCINE_CENTER
        if agent.today_activity == "grocery" and MALL.is_open(hour, day):
            return MALL
        if agent.today_activity == "park" and PARCO.is_open(hour, day):
            return PARCO

    #attività serale (dopo l'attività diurna)
    curfew = config.CURFEW_HOUR  #orario coprifuoco
    if agent.night_out_tonight and agent.role == "novax":
        curfew = 23   #se l'agente vuole uscire ed è novax, si sposta il coprifuoco
    #se l'agente decide di uscire e siamo nella finestra per l'uscita serale (dalle 20 al coprifuoco)
    if agent.night_out_tonight and hour >= 20 and hour < curfew:
        if agent.role == "novax":  #se l'agente è novax, si reca prima al bar (se aperto)
            if BAR.is_open(hour, day):
                return BAR
            #I no-vax ignorano le chiusure da lockdown del parco: ci vanno comunque.
            return PARCO   #se il bar chiuso, va al parco
        if BAR.is_open(hour, day):  #per gli altri agenti, si controlla prima se il bar è aperto
            return BAR
        if PARCO.is_open(hour, day):   #si controlla se il parco è aperto
            return PARCO

    return agent.home   #altrimenti, l'agente resta a casa la sera


#routine pianificata (usata da Truman prima della fase 1 di lockdown)
def scripted_policy(agent):
    activity = getattr(agent, "today_activity", "home")
    if activity == "grocery":
        intended = "grocery"
    elif activity == "vaccine":
        intended = "vaccine"
    elif activity == "park":   #il parco rientra nella categoria "social"
        intended = "social"
    else:
        intended = "home"
    return {  #genera un dizionario on gli stessi campi usati per DailyPolicy
        #se l'attività prevista non è "casa", la socialità è alta (altrimenti bassa)
        "sociability_today": 0.55 if intended != "home" else 0.05,
        "wants_vaccine": activity == "vaccine",
        #la tolleranza al richio dipende dalla personalità giornaliera (e quindi dall'attività)
        "risk_tolerance": 0.45 if agent.personality == "estroverso" else 0.2,
        "intended_place": intended,
        "reason": f"Routine iniziale gruppo {agent.schedule_offset}, attivita={activity}",
    }
