import random   #libreria per la generazione di numeri casuali 

#Agente e' un abitante della citta': tipo di cittadini (normale / giovane / no-vax),
#gruppo di routine (timer sfasato) e stato di salute.
#I bot seguono sempre il codice in routines.py. Il cittadino LLM, fino al
#primo lockdown, usa lo stesso codice; dopo decide cotramite Gemini.

from .city import HOME_CELLS, bfs_path   #importo la lista di celle relative alle case 
# bfs_path per calcolare il percorso più breve tra due punti 

#importa luoghi definiti nel file poi.py (point of interest)
from .poi import PointOfInterest, HOSPITAL, VACCINE_CENTER, SOCIAL_POIS, MALL

#importa gli stati di salute stabiliti (sano, esposto, infetto, rimosso, deceduto)
#aggiunge anche informazioni come la velocità di movimento, le ore in cui resta in un luogo 
#l'ora di risveglio e il range di ore d'incubazione del virus
from .config import (
    S, E, I, R, D,
    AGENT_SPEED, SOCIAL_STAY_HOURS,
    WAKE_HOUR,
    INCUBATION_HOURS,
)
from . import config   #importo tutte le costanti di sistema 
from . import routines #importo la logica di comportamento dei bot


#funzione che decide il tipo di cittadino di un agente o bot, scegliendo a sorte il ruolo e l'età
def _roll_role(agent_id):
    #controllo se l'agente è Truman (che dev'essere sempre assegnato alla categoria jung)
    if agent_id == config.LLM_CITIZEN_ID:                   #controllo se l'agente e' il cittadino LLM (id 0)
        return "young", False, random.randint(22, 32)       #se si assegno ruolo "young", non novax, eta' casuale tra 22 e 32
    
    r = random.random()    #genero un numero casuale (da 0 a 1) usato per decidere il ruolo 
    if r < config.NOVAX_FRACTION:                           #se il numero casuale e' minore della frazione di no-vax
        return "novax", True, random.randint(25, 55)        #assegno ruolo "novax", novax True, eta' casuale tra 25 e 55
    
    if r < config.NOVAX_FRACTION + config.YOUNG_FRACTION:   #se il numero casuale e' minore della somma delle frazioni di no-vax e giovani
        return "young", False, random.randint(18, 35)       #assegno ruolo "young", non novax, eta' casuale tra 18 e 35
    
    return "normal", False, random.randint(36, 60)          #assegno ruolo "normal", non novax, eta' casuale tra 36 e 60


#funzione per i parametri epidemiologici di ciascun ruolo 
#is_citizen serve per abbassare le statistiche di morte o infezione grave di Truman (il cittadino)
def _health_profile(role, is_citizen):
    # Giovani (e l'agente) guariscono piu' spesso. I no-vax si ammalano
    # piu' facile, restano infetti di piu', ma muoiono di meno.
    if role == "young":
        profile = {
            "severe_prob": 0.05 if is_citizen else 0.07,    #probabilità di malattie gravi
            "death_hospital": 0.06 if is_citizen else 0.10,  #morte da ricovero
            "death_no_hospital": 0.18 if is_citizen else 0.28, #morte senza ricovero
            "death_mild": 0.001 if is_citizen else 0.003,   #morte damalattia lieve
            "illness_hours": (96, 192),   #range (n ore) di durata della malattia
            "infection_mult": 0.9,   #parametri che rende i giovani meno soggetti all'infezione
        }
    elif role == "novax":    #i novax avrano parametri più alti per far progredire l'infezione
        profile = {
            "severe_prob": 0.14,
            "death_hospital": 0.12,
            "death_no_hospital": 0.32,
            "death_mild": 0.004,
            "illness_hours": (180, 360),
            "infection_mult": 1.45,
        }
    else:     #per i cittadini normal, si usano i valori standard definiti in config
        profile = {
            "severe_prob": config.SEVERE_PROB_BASE,
            "death_hospital": config.DEATH_PROB_HOSPITAL,
            "death_no_hospital": config.DEATH_PROB_NO_HOSPITAL,
            "death_mild": config.DEATH_PROB_MILD,
            "illness_hours": None,
            "infection_mult": 1.0,
        }
    if config.LETHAL_OUTBREAK: #caso di outbreak letale: aumento della probabilita' di malattia grave e morte, riduzione della durata della malattia, aumento della probabilita' di infezione
        factor = config.LETHAL_ROLE_FACTOR.get(role, 1.0) #regolatore di mortalità
        #alza la mortalità del virus in base al ruolo del cittadino 
        profile["severe_prob"] = min(0.97, config.LETHAL_SEVERE_PROB * factor)
        profile["death_hospital"] = min(0.97, config.LETHAL_DEATH_HOSPITAL * factor)
        profile["death_no_hospital"] = min(0.99, config.LETHAL_DEATH_NO_HOSPITAL * factor)
        profile["death_mild"] = min(0.6, config.LETHAL_DEATH_MILD * factor)
        profile["illness_hours"] = config.LETHAL_ILLNESS_HOURS
        profile["infection_mult"] = config.LETHAL_INFECTION_MULT.get(role, 1.0)
    return profile    #restituisce il "dizionario" di tutti i ruoli con parametri per l'agente


class Agent:
    def __init__(self, agent_id):   #costruttore degli agenti
        self.id = agent_id     #id univoco
        self.home = random.choice(HOME_CELLS)    #casa di appartenenza scelta randomicamente
        self.pos = self.home    #posizione iniziale dell'agente impostata nella casa di appartenenza
        self.leave_at = None   

        self.personality = random.choices(
            ["introverso", "estroverso"], weights=[0.4, 0.6]
        )[0]   #sceglie casualmente se l'agente sarà introverso (probabilità 40%), o estroverso (60%)
        self.sociability = 0.15 if self.personality == "introverso" else 0.6
        #se l'agente è introverso, avrà una socialità bassa (0.15), mentre sarà alta (0.6) se è estroverso

        #chiamo la funzione sopra per assegnare ruolo, stato (novax o no) ed età
        self.role, self.novax, self.age = _roll_role(agent_id)
        self.vaccinated = False    #inizialmente l'agnete non sarà ancora vaccinato
        #calcolo per lo sfasamento dei timer dei gruppi di agenti
        self.schedule_offset = agent_id % config.N_SCHEDULE_GROUPS
        self.night_seed = random.randint(0, 10)   #per decidere se l'agente esce o meno di sera
        self.today_activity = "home"  #flag 1 sulla posizione dell'agente 
        self.night_out_tonight = False  #flag 2 per sapere se l'agente uscirà la sera o no
        self.day_activity_done = False  #flag 3 per sapere se l'attività della giornata è stata completata

        #richiamo ora la funzione per ottener il profilo sanitario dell'agente
        profile = _health_profile(self.role, agent_id == config.LLM_CITIZEN_ID)
        self.severe_prob = profile["severe_prob"]
        self.death_hospital = profile["death_hospital"]
        self.death_no_hospital = profile["death_no_hospital"]
        self.death_mild = profile["death_mild"]
        self.illness_hours_range = profile["illness_hours"]
        self.infection_mult = profile["infection_mult"]

        self.state = S    #lo stato di salute iniziale è sempre S (sano con possibilità di infettarsi)
        self.state_timer = 0  #contatore per sapere da quanto tempo l'agente è nello stato attuale
        self.incubation_time = 0  
        self.illness_time = 0
        self.severe = False
        self.hospitalized = False

        self.destination = self.home    #destinazione di partenza dell'agente (casa)
        self.path = []    #lista di celle del percorso calclato da bfs_path, inizialmente vuota


        #dati di tracciamento specifici per Truman
        self.last_grocery_day = 0    #ultmimo giorno in cui ha fatto la spesa
        self.last_vaccine_check_day = -1    #ultima volta che ha controllato la disponibilità del vaccino
        self.yesterday_note = "Nessun evento ancora."    #riassunto di cosa è successo il giorno prima
        self.last_policy_day = None       #giorno in cui è stata generata l'ultima DailyPolicy
        #per calcolare se sono passati abbasatnza giorni per la nuova decisione
        self.state_at_last_policy = None   #stato di salute percepito nell'ultima decisione
        #per rilevare se lo stato di salute è cambiato
        self.daily_policy = None   #variabile in cui si salverà la DailyPolicy restituito da Gemini

    def plan_day(self, day, phase):   #chiamato ogni nuovo giorno di simulazione 
        routines.plan_day(self, day, phase)   #funzione delegata per la logica di pianificazione
        self.day_activity_done = False    #reset dei flag giornalieri 
        self.leave_at = None


    def uses_script(self):
        # Bot: sempre script. Truman: script solo prima del primo lockdown.
        if self.id != config.LLM_CITIZEN_ID:
            return True   # i bot usano sempre lo script definito
        phase = getattr(getattr(self, "model_ref", None), "lockdown_phase", 0)  #recuper la fase di lockdown
        return phase == 0    #verifica se siamo nella fase pre lockdown 
    #se la condizione è vera, Truman segutirà lo script, altrimenti inizierà a prendere decisioni


#Metodi statici di supporto

    @staticmethod
    def _target_cells(target):
        if isinstance(target, PointOfInterest):   #se il punto di destinazione (trget) è complesso 
            #cioè occupa più celle
            return target.cells  #restituisce l'insieme di celle che lo compongono
        return {target}   #se il traget non è composto da più celle, inapsula la sola cella in un elemento

    def _has_arrived(self, target):    #controla la posizione attuale dell'agente   
        return self.pos in self._target_cells(target)
    #verifica se la posizione dell'agente è nell'insime di celle che compongono la destinazione

    def infect(self):    #passaggio dell'utente da S a E
        if self.state != S:
            return    #se non è in S, esce (non si può infettare 2 volte)
        self.state = E
        self.state_timer = 0    #imposta il timer a 0 (è appena passato a un nuovo stato)
        self.incubation_time = random.randint(*INCUBATION_HOURS)
        #estrae il min e max di INCUBATION_HOURS e calcola un tempo di incubazione randomico 

    def update_health(self, hospital):
        self.state_timer += 1    #incrementa il timer di stato dell'agente di 1 ora

        # se l'agente non ha un intervallo di durata della malattia, usa quello standard
        hours_range = self.illness_hours_range or config.ILLNESS_HOURS
        #se il tempo di incubazione è stato superato, passa da E ad I
        if self.state == E and self.state_timer >= self.incubation_time:
            self.state = I
            self.state_timer = 0
            self.illness_time = random.randint(*hours_range)  #calcola un tempo casuale di infezione
            self.severe = random.random() < self.severe_prob
            #si stabilisce randomicamente se il caso sarà grave o no, generando un numero da 0 a 1
            #se il numero è minore della probabilità di gravità configurata, il caso è severo

        #Se l'agente è infetto e la durata della malattia è terminata 
        elif self.state == I and self.state_timer >= self.illness_time:
            #la probabilità di morte dipende da 2 fattori combinati:
            #se il caso è grave e se è stato ricoverato 
            #si definisco 3 casi (con probabilità di morte già calcolata)
            if self.severe and self.hospitalized:   #caso grave e ricoverato
                death_p = self.death_hospital
            elif self.severe and not self.hospitalized:  #caso grave e non ricoverato
                death_p = self.death_no_hospital
            else:    #caso non grave
                death_p = self.death_mild

            if random.random() < death_p:   #si stabilisce casualmente se l'agente muore o no
                self.state = D
            else:
                self.state = R

            if self.hospitalized:  #indipendentemente dall'esito, l'agente viene rimosso dall'ospedale
                hospital.discharge(self)
                self.hospitalized = False   #cambia lo stato dell'agente (non più ricoverato)

    def decide_destination(self, hour, day):  #metodo per il controllo destinazione dell'agente
        if self.state == D:   #priorità massima, se l'agente è morto, resta fermo dov'è
            return self.pos

        if self.hospitalized:  #se l'agente è ricoverato, resta in ospedale (vincolo hard)
            return HOSPITAL

        phase = getattr(getattr(self, "model_ref", None), "lockdown_phase", 0)  #recupero fase lockdown
        curfew = config.CURFEW_HOUR   #orario del coprifuoco
        if self.night_out_tonight and (self.role == "novax" or phase == 0):
        #se l'agente ha deciso di passare una serata fuori, si verifica se l'agente è novax o 
        #siamo nella fase 0; se una delle due è vera, si sposta il coprifuoco almeno fino alle 23
            curfew = max(curfew, 23)
        if hour >= curfew or hour < WAKE_HOUR:
            #se è passato il coprifuoco e siamo prima dell'orario di risveglio (di notte)
            return self.home    #l'agente deve tornare a casa 

        #se l'agente è infetto, in forma grae e non è ricoverano
        if self.state == I and self.severe and not self.hospitalized:
            if HOSPITAL.has_room():   #se l'ospedale ha stanze disponibili
                return HOSPITAL   #l'agente si reca in ospedale (indipendentemente dalla policy)
            return self.home     #se l'ospedale è pieno, resta a casa

        #se l'agente sta già compinedo un percorso verso una destinazione 
        if self.path and not self._has_arrived(self.destination):
            return self.destination  #continua verso la destinazione senza ricalcolare nuovi percorsi
        
        #se l'agente è in un punto sociale e non è ancora l'ora di andarsene, resta lì
        if (self.destination in SOCIAL_POIS and self._has_arrived(self.destination)
                and self.leave_at is not None and hour < self.leave_at):
            return self.destination

        if self.uses_script():   #se l'agente dev usare lo stesso script dei bot
            return routines.scripted_place(self, hour, day, phase)
        #delega la decisione a routines.scripted_plac, senza coinvolgere l'LLM

        #se si arriva fino a qui, Truman deve prendere decisioni autonome

        policy = getattr(self, "daily_policy", None) or {}   #recupero la daily_policy
        #generata da Gemini o riutilizzata dalla cache, o un dizionario vuoto come fallback se 
        #non esiste ancora

        #si estraggono dalla policy le caratteristiche dell'agente, se non ci sono si usano quelle standard
        sociability = policy.get("sociability_today", self.sociability)
        intended = policy.get("intended_place", "auto")

        #traduzione dell'intezione dichiarata da Gemini
        if intended == "home":   #se l'intenzione è "casa" si abbassa la socialità (valore quasi nullo)
            sociability = min(sociability, 0.02) #anche se gemini per errore indica un valore alto
        elif intended == "hospital" and self.state == I and HOSPITAL.has_room():
            return HOSPITAL
        elif intended == "vaccine" and VACCINE_CENTER.is_open(hour, day) and not self.novax and not self.vaccinated and self.state != "I": 
            return VACCINE_CENTER   #ittadini infetti non possono vaccinarsi
        elif intended == "grocery" and MALL.is_open(hour, day):
            return MALL
        elif intended == "social":   #se l'intenzione è "cocievole", si alza la socievolezza
            sociability = max(sociability, 0.45)

        # Niente codice extra "vai al vaccino": se lo vuole, sta in intended_place.

        #decisione in base alla socialità (se non è stata determinata una destinazione sopra)
        open_social = [p for p in SOCIAL_POIS if p.is_open(hour, day)]  #valuta i punti aperti
        if open_social and random.random() < sociability:
            return random.choice(open_social)
        #più alta è la socialità, più sarà probabile che l'agente scelga un luogo sociale dove recarsi

        return self.home    #se nessuna condizione si verifica, l'agente resta a casa

    #gestione del movimento dell'agente, dopo che si è decisa la destinazione
    def move_one_step(self, hour, day):    
        if self.state == D:    #se l'agente è morto, non si può muovere
            return

        target = self.decide_destination(hour, day)   #chiama la funzione per sapere la destinazione

        if target == self.destination and self._has_arrived(target): #destinazione già raggiunta
            self.path = []   #non serve muoversi
            social = target in SOCIAL_POIS or target is VACCINE_CENTER
            if social:     #se il luogo target è un punto sociale o centro vaccinale 
                if self.leave_at is None:   #se non è ancora stato deciso un periodo di permanenza
                    stay = random.randint(*SOCIAL_STAY_HOURS)   #si assegna un periodo casuale
                    self.leave_at = hour + stay    #si calcola il momento in cui l'agente se ne va
                    return
                if hour < self.leave_at:    #se l'orario di uscita non è ancora arrivato, esce
                    return
                self.leave_at = None    #se l'ora di uscit è arrivata, si resettano i parametri
                self.day_activity_done = True
                self.destination = self.home
            return

        #calcolo se il percorso può attraversare l'area dell'ospedale
        allow_hospital = self.hospitalized or (target is HOSPITAL) or HOSPITAL.contains(self.pos)
        #l'agente non dovrebbe tagliare per l'ospedale se non è diretto lì

        #se la destinazione cambia o non esiste ancoraun percorso calcolato
        if target != self.destination or not self.path:
            self.destination = target    #si aggiorna la destinazione
            self.leave_at = None      #resetto leave_at
            self.path = bfs_path(self.pos, self._target_cells(target), allow_hospital=allow_hospital)
            #ricalcolo il percorso, rispettando il vincolo dell'ospedale

        steps = min(AGENT_SPEED, len(self.path))   #si muove l'agente lungo il percorso calcolato
        #steps è il numero di celle da percorrere
        for _ in range(steps):   #spostamento dell'agente sulle N celle (steps)
            self.pos = self.path.pop(0)
