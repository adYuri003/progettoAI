# Modello che simula la pandemia: popolazione, passo orario, lockdown, statistiche.

import os
import random
import time

from . import config
from .agent import Agent
from .llm_agent import LLMAgent, fetch_daily_policy, unlock_phase_knowledge
from .llm_tools import set_active_world
from .lockdown import apply_phase, maybe_advance_lockdown
from .poi import HOSPITAL, MALL, VACCINE_CENTER
from .routines import scripted_policy


class PandemicModel:
    def __init__(self):    #resetto le liste di occupazione dell'ospedale, del centro vaccinale e del giorno di disponibilità vaccino
        HOSPITAL.occupants = []
        VACCINE_CENTER.occupants = []
        VACCINE_CENTER.open_from_day = config.VACCINE_START_DAY

        self.lockdown_phase = 0    #imposta la fase di lockdown a 0 (fase pre lockdown)
        self.lockdown_events = []   #lista di eventi (passaggio di fase) inizialmente vuota
        self.vaccine_opened_on_day = None   #centro vaccinale non ancora aperto
        apply_phase(self, 0)    #applio le regole della fase 0 (funzione in lockdown.py)

        self.agents = []   #lista agenti in città
        for i in range(config.N_AGENTS):   #per ogni agente presente
            agent = LLMAgent(i) if i == config.LLM_CITIZEN_ID else Agent(i)
            agent.model_ref = self    #ogni agnte riceve un riferimento al modello in cui è contenuto
            self.agents.append(agent)
        #se l'agente è Truman, si crea un istanza di LLMAgent
        #altrimenti si crea un istanza di Agent per gli altri cittadini

        # L'agente osservato non parte gia' infetto: e' giovane e deve avere
        # tempo di seguire la routine e poi imparare.
        #pool contiene una lista di agenti (tranne Truman)
        pool = [a for a in self.agents if a.id != config.LLM_CITIZEN_ID]
        n_seed = min(config.INITIAL_INFECTED, len(pool))  #calcola il numero di agenti infetti iniziali
        #il numero di infetti iniziale non può andare oltre i cittadini disponibili

        for a in random.sample(pool, n_seed):   #random.sample evita di estrarre 2 volte lo stesso agente
            a.state = config.I   #per ciascuno degli agenti estratti, si forza lo stato ad I
            hours_range = a.illness_hours_range or config.ILLNESS_HOURS
            a.illness_time = random.randint(*hours_range)
            #calcolo casualmente il tempo in cui i pazienti 0 saranno infetti (malati)
            a.severe = random.random() < a.severe_prob  #scelgo se il caso è grave (randomicamente)

        self.hour = 0
        self.day = 0
        #dizionario di chiavi associate a liste vuote, riempite di volta in volta con gli eventi 
        #della simulazione (ogni chiave è uno stato di salute)
        #ogni lista accumulerà il conteggio di agenti nel relativo stato
        self.history = {s: [] for s in (config.S, config.E, config.I, config.R, config.D)}
        self.hospital_history = []   #lista occupazione ospedale
        self.vaccinated_history = []  #lista numero di vaccinati nel tempo
        self.llm_policy_history = {}  #lista di policy dell'LLM
        self.llm_call_count = 0   #contatore delle chiamate a Gemini
        self.frame_history = []   #per animazione visiva

        set_active_world(self, self.citizen)

    @property   #trasformo un metodo in un attributo (può essere chiamato senza parametri)
    def citizen(self):   #restituisce l'agente speciale in lista
        return self.agents[config.LLM_CITIZEN_ID]

    def _note_yesterday(self, agent):   #funzione per costruire il riassunto della gironata precedente
        bits = []   #lista degli eventi rilevanti accaduti

        #controlliamo se lo stato di salute dell'agente è variato 
        if agent.state != getattr(agent, "prev_health", agent.state):
            #aggiungo il nuovo stato di salute
            bits.append(f"salute {getattr(agent, 'prev_health', '?')} -> {agent.state}")
        if agent.vaccinated and not getattr(agent, "prev_vaccinated", False):
            #se l'agente ha ricevuto il vaccino, aggiungo l'informazione
            bits.append("vaccinato oggi")
        if agent.hospitalized:
            #se l'agente è stato ricoverato, lo segno come "in ospedale"
            bits.append("in ospedale")
        #cotruisco la stringa finale se ho accumulato eventi nella lista bits
        agent.yesterday_note = "; ".join(bits) if bits else "Nessun evento particolare."
        #modifico lo stato di salute con quello attuale per il prossimo controllo
        agent.prev_health = agent.state
        #aggiorno lo stato di vaccinazione nel caso sia cambiato 
        agent.prev_vaccinated = agent.vaccinated

    def _update_citizen_policy(self):   #aggiornamento policy
        citizen = self.citizen   #recupero il cittadino LLM, con la funzione sopra
        if citizen.state == config.D:   #se il cittadino è morto, non compio aggiornamenti
            return

        # Prima del lockdown il cittadino copia i bot del suo gruppo.
        # Dal primo lockdown in poi chiama Gemini e non riceve i codici extra.
        if citizen.uses_script():  #se il cittadino usa lo script, siamo ancora in fase 0
            policy = scripted_policy(citizen)
            used_llm = False
        else:    #altrimenti, siamo in una fase pandemica
            #si richiama la funzione per il recupero della policy quotidiana
            #(senza eventi significativi, verrà riutilizzata la policy del giorno prima)
            policy = fetch_daily_policy(citizen, self.day)
            reason = policy.get("reason") or ""  #verifico se si riusa la vecchia policy con una reason specificata
            reused = "riuso cache" in reason  
            used_llm = not reused   #se non è stato incluso un messaggio "riuso cache" nella nuova
            #policy, è stata effettuata una nuova chiamata a Gemini
            if used_llm:   #se si è utilizzato l'LLM (chiamata a Gemini)
                self.llm_call_count += 1   #si aggionra il contatore delle chiamate
                time.sleep(int(os.getenv("LLM_SLEEP_SECONDS", "40")))  #pausa artificiale dell'LLM
                #questo tempo è stato impostato per non superare le risorse gratuite fornite da Gemini

        #aggiornamento degli attributi dell'agente con i dati della policy (anche se riutilizzata)
        citizen.daily_policy = policy 
        citizen.last_policy_day = self.day
        citizen.state_at_last_policy = citizen.state
        reason = policy.get("reason") or ""

        #se citizen.id non è ancora una chiave presente nel dizionario llm_policy, la creo con 
        #setdefault (la creo con il valore di default [])
        #questo dizionario è usato per analizzare come il comportamento di Truman cambia nel tempo
        self.llm_policy_history.setdefault(citizen.id, []).append({
            "day": self.day,
            "sociability": policy["sociability_today"],
            "risk_tolerance": policy["risk_tolerance"],
            "wants_vaccine": policy["wants_vaccine"],
            "intended_place": policy.get("intended_place"),
            "reason": reason,
            "health_state": citizen.state,
            "used_llm": used_llm,
            "lockdown_phase": self.lockdown_phase,
        })

    def step(self):   #passo orario nella simulazione 
        if self.hour == 0:  #inizio giornata (ora 0 del nuovo giorno)
            changed = maybe_advance_lockdown(self)  #controllo se il lockdown deve avanzare
            if changed:   #se la fase è cambiata
                unlock_phase_knowledge(self.lockdown_phase)  #sbloco i file per quella fase
            for agent in self.agents:   #per ogni agente presente
                agent.plan_day(self.day, self.lockdown_phase)  #si painifica la giornata dell'agente
            self._note_yesterday(self.citizen)   #si verificno i cambiamenti dal giorno precedente
            self._update_citizen_policy()   #si richiede la nuova policy dell'agente

        for agent in self.agents:   #per ogni agente 
            agent.move_one_step(self.hour, self.day)  #ogni agente esegue un movimento 

        #la lista dell'ospedale eve contentere solo chi non è morto 
        for poi in (HOSPITAL, VACCINE_CENTER):
            poi.occupants = [a for a in poi.occupants if a.state != config.D]

        #se l'agente è morto, salto al prossmo ciclo
        for agent in self.agents:
            if agent.state == config.D:
                continue

            #si verifica se l'agente è diretto all'ospedale, in condizioni gravi
            if (HOSPITAL.contains(agent.pos) and agent.state == config.I and agent.severe
                    and not agent.hospitalized):  #verifico se l'agente non è ancora ricoverato
                if HOSPITAL.can_accept(agent):  #verifico se l'ospedale ha posto per l'agente
                    HOSPITAL.admit(agent)   #l'ospedale accetta l'agente 
                    agent.hospitalized = True  #l'agente viene contrassegnato come ricoverato

            #se l'agente è diretto al centro vaccinale, non è stato ancora vaccinato, non è novax
            #e il centro vaccinale è effettivamente aperto 
            if (VACCINE_CENTER.contains(agent.pos) and not agent.vaccinated
                    and not agent.novax and VACCINE_CENTER.is_open(self.hour, self.day)):
                agent.vaccinated = True  #l'agente viene contrassegnato come vaccinato

            #se l'agente è diretto al supermercato
            if MALL.contains(agent.pos):
                agent.last_grocery_day = self.day  #si aggiorna l'ultimo giorno di spesa

        cells = {}   #dizionario che raggruppa gli agenti perposizione 
        for agent in self.agents:
            if agent.state == config.D:   #l'agente morto non viene considerato
                continue
            cells.setdefault(agent.pos, []).append(agent)
            #per ogni agente vivo in una cella, si aggiunge l'agente nella lista
            # #si ottiene un dizionario con i gruppi di agenti presenti in ogni cella 

        for cell_agents in cells.values():   #per ogni agente in una stessa cella
            #si separano gli agenti infetti da quelli sani
            infected_here = [a for a in cell_agents if a.state == config.I]
            susceptible_here = [a for a in cell_agents if a.state == config.S]

            #se nella stessa cella ho sia agenti infetti I che sani S
            if infected_here and susceptible_here:
                for s_agent in susceptible_here:   #per ogni agente S nella cella
                    #la probabilità di infezione dell'agente si moltiplica per il suo fattore
                    #di infezione (diverso per gruppo di agenti)
                    prob = config.INFECTION_PROB * s_agent.infection_mult
                    if s_agent.vaccinated:   #se l'agente è vaccinato 
                        #la probabilità viene ridotta in base all'efficacia del vaccino
                        prob *= (1 - config.VACCINE_EFFICACY) 
                    #probabilità di non essere contagiati da un infetto, moliplicata per il 
                    #numero di infetti, perottenere la probabilità di nonn essere contagiato 
                    #da nessuno degli infetti presenti nella cella
                    prob_no_infection = (1 - prob) ** len(infected_here)

                    #viene scelto randomicamente se il cittadino si ammala o no stando a contatto
                    #con infetti (in una stessa cella), in base al dato appena calcolato
                    if random.random() > prob_no_infection:
                        s_agent.infect()

        for agent in self.agents:   #avanzamento dello stato della malattia
            agent.update_health(HOSPITAL)

        #dizionario di conteggio per ogni stato
        counts = {config.S: 0, config.E: 0, config.I: 0, config.R: 0, config.D: 0}
        for agent in self.agents:
            counts[agent.state] += 1   #per ogni agente, si incrementa il conteggio in base al suo stato attuale
        for k in self.history:
            self.history[k].append(counts[k])  #aggiungo alla hystori il conteggio per ogni stato di salute
        self.hospital_history.append(len(HOSPITAL.occupants))  #aggiungo il numero di occupanti dell'ospedale
        #aggiungo il numero di persone vaccinate
        self.vaccinated_history.append(sum(1 for a in self.agents if a.vaccinated))
        #costruisco lo stato completo di un determinato istante (per l'animazione)
        self.frame_history.append({
            "day": self.day,
            "hour": self.hour,
            "xs": [a.pos[0] for a in self.agents],
            "ys": [a.pos[1] for a in self.agents],
            "states": [a.state for a in self.agents],
            "is_citizen": [isinstance(a, LLMAgent) for a in self.agents],  #differenzia truman dagli altri cittadini
            "hospital_occupants": len(HOSPITAL.occupants),
            "vaccine_active": self.vaccine_opened_on_day is not None and self.day >= self.vaccine_opened_on_day,
            "lockdown_phase": self.lockdown_phase,
            "citizen_state": self.citizen.state,
        })

        #incremento dell'ora
        self.hour = (self.hour + 1) % config.HOURS_PER_DAY  
        #config.HOURS_PER_DAY evita il superamento di 24 ore, riportando il contatore a 0
        if self.hour == 0:  #se il contatore torna a 0,s i incrementa il giorno
            self.day += 1

    def run(self, total_hours):   #chiama self.step() un numero di volte pari alle ore
        for _ in range(total_hours):
            self.step()