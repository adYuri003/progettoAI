#Parametri globali. Gli scenari (scenarios.py) possono sovrascrivere questi valori a runtime con apply_scenario().

import os

#Quanti agenti popolano la citta' e per quanti giorni gira la simulazione.
N_AGENTS = 150
N_DAYS = 21
HOURS_PER_DAY = 24

#Un solo abitante e' un agente Agno (id 0), decide tramite Gemini dal primo lockdown in poi. Prima segue la stessa routine dei bot giovani.
LLM_CITIZEN_ID = 0

#Nome del modello Gemini usato dal cittadino intelligente (llm_agent.py).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

#Ogni quanti giorni il cittadino richiama Gemini per aggiornare la sua policy
#(tra una chiamata e l'altra riusa la policy del giorno prima, per risparmiare quota API; un cambio di salute o di fase di lockdown forza un refresh).
LLM_DECIDE_EVERY_N_DAYS = 2

#Quante celle per passo puo' percorrere un agente quando si sposta (city.py).
AGENT_SPEED = 4
#Range di ore (min, max) che un agente resta in un luogo sociale prima di ripartire.
SOCIAL_STAY_HOURS = (1, 3)

#Ora in cui gli agenti si svegliano e ora del coprifuoco (poi aggiornata dalle fasi).
WAKE_HOUR = 5
CURFEW_HOUR = 23

#Frazioni dei tre tipi di bot: normali, giovani (stesso gruppo dell'agente) e no-vax
YOUNG_FRACTION = 0.30
NOVAX_FRACTION = 0.22
#Quanti sottogruppi con lo stesso codice ma timer sfasato (spesa in giorni diversi).
N_SCHEDULE_GROUPS = 5
#Ogni quanti giorni va a fare la spesa, a seconda della fase (i no-vax restano sul 5).
GROCERY_INTERVAL_BY_PHASE = {0: 5, 1: 7, 2: 7, 3: 6}

#Se il cittadino osservato non fa la spesa da questi giorni forza una nuova chiamata a Gemini.
CITIZEN_GROCERY_REMINDER_DAYS = 3

#Uscita serale: un seme a caso in init, poi una sera ogni N giorni.
NIGHT_OUT_MODULO = 4
NIGHT_OUT_MODULO_NOVAX = 1

#Virus "cattivo" prima del primo lockdown, poi valori da chiusure in poi.
INFECTION_PROB_PRE = 0.32
INFECTION_PROB_LOCKDOWN = 0.18
INFECTION_PROB = INFECTION_PROB_PRE
INCUBATION_HOURS = (48, 120)
ILLNESS_HOURS_PRE = (144, 280)
ILLNESS_HOURS_LOCKDOWN = (120, 240)
ILLNESS_HOURS = ILLNESS_HOURS_PRE
SEVERE_PROB_BASE = 0.18
#rischio di morte dello scenario base
DEATH_PROB_HOSPITAL = 0.30
DEATH_PROB_NO_HOSPITAL = 0.70
DEATH_PROB_MILD = 0.01
INITIAL_INFECTED = 3

#Soglie sul numero di infetti (stato I) per salire di fase.
#Le teniamo alte abbastanza da non chiudere la citta' con tre casi.
LOCKDOWN_PHASE1_INFECTED = round(N_AGENTS * 0.15)  # 15% of the population
LOCKDOWN_PHASE2_INFECTED = round(N_AGENTS * 0.35)  # 35% of the population
LOCKDOWN_PHASE3_INFECTED = round(N_AGENTS * 0.50)  # 50% of the population

#Il centro vaccinale non ha un giorno fisso: compare in fase 3.
#VACCINE_START_DAY viene scritto da lockdown.py quando la fase scatta.
VACCINE_START_DAY = 10**9
VACCINE_DAILY_PROB = 0.20
VACCINE_EFFICACY = 0.85

#Posti letto disponibili in ospedale.
HOSPITAL_CAPACITY = 50

#Stati di salute: Sano, Esposto, Infetto, Guarito, Deceduto.
S, E, I, R, D = "S", "E", "I", "R", "D"

#Funzione di utilita' per il cittadino LLM: se vede un agente in stato E (esposto, incubazione) lo percepisce come S (sano), perche' non ha sintomi e non se ne accorge.
def perceived_state(state):
    return S if state == E else state

#Scenario attualmente applicato e id di sessione usato da Agno per la memoria persistente del cittadino tra una run e l'altra.
ACTIVE_SCENARIO = "baseline"
SESSION_ID = "citizen_0"
USER_ID = "citizen_0"

#Scenario Lethal 
LETHAL_OUTBREAK = False  

#parametri dello scenario lethal
LETHAL_SEVERE_PROB = 0.55
LETHAL_DEATH_HOSPITAL = 0.45
LETHAL_DEATH_NO_HOSPITAL = 0.88
LETHAL_DEATH_MILD = 0.04
LETHAL_ILLNESS_HOURS = (72, 150)

LETHAL_ROLE_FACTOR = {
    "young": 0.55,
    "normal": 1.0,
    "novax": 1.7,
}
LETHAL_INFECTION_MULT = {
    "young": 1.0,
    "normal": 1.2,
    "novax": 1.8,
}