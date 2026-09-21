#Fasi di lockdown: partono quando ci sono abbastanza infetti

from . import config
from .poi import BAR, HOSPITAL, MALL, PARCO, VACCINE_CENTER   #punti di interesse 


def infected_count(agents):   #funzione per il conteggio dei cittadini infetti 
    return sum(1 for a in agents if a.state == config.I)


def phase_for_infected(n_infected, current_phase):
    target = current_phase   #fase attuale 
    if n_infected >= config.LOCKDOWN_PHASE3_INFECTED:   #se il numero di infetti è suffiente per la fase 3
        target = 3   #imposto a fase 3
    elif n_infected >= config.LOCKDOWN_PHASE2_INFECTED:
        target = 2
    elif n_infected >= config.LOCKDOWN_PHASE1_INFECTED:
        target = 1
    target = max(current_phase, target)   #prende la fase maggiore tra quella attuale e quella calcolata
    #in pratica, la fase pandemica non decresce mai, resta ferma o avanza, ma non torna indietro
    return min(target, current_phase + 1)
#IMPORTANTE: senza questa riga, la simulazione passava da una fase bassa (es. 0 o 1) alla massima (3)
#senza passare per la due; con questa soluzione grantiamo un passaggio graduale tra le varie fasi pandemiche


#azione vera al cambiamento della fase pandemica
def apply_phase(model, phase):
    model.lockdown_phase = phase   #recupero pandemica

    if phase == 0: #parametri impostati ai valori pre lockdown
        config.INFECTION_PROB = config.INFECTION_PROB_PRE  #probabilità di infezione
        config.ILLNESS_HOURS = config.ILLNESS_HOURS_PRE    #durata infezione
        config.CURFEW_HOUR = 23   #orario coprifuoco 
        BAR.open_hour, BAR.close_hour = 18, 23   #orari bar 
        MALL.open_hour, MALL.close_hour = 9, 20  #orari supermercato
        PARCO.open_from_day = 0    #apertura parco (aperto fino al giorno 0, quindi sempre aperto)
        BAR.open_from_day = 0    
    elif phase == 1:    #parametri impostati ai valori del lockdown di tipo 1
        config.INFECTION_PROB = config.INFECTION_PROB_LOCKDOWN
        config.ILLNESS_HOURS = config.ILLNESS_HOURS_LOCKDOWN
        config.CURFEW_HOUR = 22
        #Fase 1: meno restrittivo, si esce ancora; bar e parco aperti ma con orari ridotti.
        PARCO.open_from_day = 0
        BAR.open_from_day = 0
        BAR.open_hour, BAR.close_hour = 18, 21
        MALL.open_hour, MALL.close_hour = 9, 19
    elif phase == 2:    #parametri impostati ai valori del lockdown di tipo 2
        config.INFECTION_PROB = config.INFECTION_PROB_LOCKDOWN
        config.ILLNESS_HOURS = config.ILLNESS_HOURS_LOCKDOWN
        config.CURFEW_HOUR = 21
        #Fase 2: niente bar ne' parco, ma la spesa resta libera durante il giorno.
        BAR.open_from_day = 10**9   #bar aperto dal miliardesimo giorno (non sarà mai aperto in queste fasi)
        PARCO.open_from_day = 10**9
        MALL.open_hour, MALL.close_hour = 9, 19
    else:    #parametri impostati ai valori del lockdown di tipo 3
        config.INFECTION_PROB = config.INFECTION_PROB_LOCKDOWN
        config.ILLNESS_HOURS = config.ILLNESS_HOURS_LOCKDOWN
        config.CURFEW_HOUR = 20
        #Fase 3: lockdown duro. Bar e parco chiusi, spesa solo in una fascia oraria ristretta.
        BAR.open_from_day = 10**9
        PARCO.open_from_day = 10**9
        MALL.open_hour, MALL.close_hour = 10, 13
        #Il centro vaccinale compare solo in fase 3 e resta visibile da qui.
        if model.vaccine_opened_on_day is None:   #centro vaccinale non ancora aperto (primo ingresso nella fase 3)
            model.vaccine_opened_on_day = model.day   #il centro vaccinale diventa disponibile 
            VACCINE_CENTER.open_from_day = model.day
            config.VACCINE_START_DAY = model.day

    HOSPITAL.capacity = config.HOSPITAL_CAPACITY


#funzione richiamata ogni giorno per controllare il possibile avanzamento della fase
def maybe_advance_lockdown(model):
    n = infected_count(model.agents)    #conta il numero di infetti
    new_phase = phase_for_infected(n, model.lockdown_phase)  #verifica quale dovrebbe essere la nuova fase
    if new_phase == model.lockdown_phase:  #se la fase attuale è uguale a quell rilevata 
        return False    #non si fa nulla
    apply_phase(model, new_phase)  #se la fase è cambiata, applico le variazioni dei parametri

    #registro l'evento in una lista
    model.lockdown_events.append({"day": model.day, "phase": new_phase, "infected": n})
    #stampo un messaggio per notificare il passaggio da una fase ad un altra
    print(f"Lockdown fase {new_phase} (giorno {model.day}, infetti={n})")
    return True
