#Unico agente intelligente: un cittadino Agno con tool, schema, memoria e RAG.
#Fino al primo lockdown copia la routine dei bot giovani ma inseguito decide da solo la propria giornata, usando i tool e la knowledge.
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from pydantic import BaseModel, Field

from . import config
from .agent import Agent as BaseAgent
from .llm_tools import build_snapshot, set_active_world


#Schema strutturato da passare come output_schema all'agente LLM. Gemini restituira' un oggetto DailyPolicy che verra' validato da pydantic.
#Pydantic garantisce che i valori siano coerenti e fornisce un dizionario con i valori validi da usare nella simulazione.
class DailyPolicy(BaseModel):   #grazie a questo schema, l'output genrato sarà sempre in una forma prevedibili e controllata
    #si utilizza BaseModel per verificare che i dati generati rispettino i vincoli
    #Propensione a uscire e socializzare oggi, tra 0 e 1
    sociability_today: float = Field(
        ge=0, le=1, description="Propensione a uscire e socializzare oggi"
    )   #LLM è vincolato a restituire un valore compreso tra 0 e 1
    #la description viene inviata a Gemini come parte dello schema, per spiegare cosa deve rappresentare quel campo
    #ge = greater or equak, le = less or equal

    #Propensione a cercare il vaccino oggi, tra vero e falso
    wants_vaccine: bool = Field(description="Se oggi cerchera' il centro vaccinale")

    #Propensione a rischiare esposizione oggi, tra 0 e 1
    risk_tolerance: float = Field(
        ge=0, le=1, description="Quanto e' disposto a rischiare esposizione"
    )

    #Destinazione preferita oggi, tra home, grocery, social, hospital, vaccine
    intended_place: str = Field(
        description="Destinazione preferita: home, grocery, social, hospital, vaccine"
    )

    #Motivazione in italiano
    reason: str = Field(description="Motivazione in italiano da 20 a 400 caratteri")


class LLMAgent(BaseAgent):
    pass   #eredita le funzionalità di BaseAgent (cioè Agent)


_agno_agent = None          #Contiene l'istanza dell'agente LLM Gemini + LanceDB, creata al primo run della simulazione o di AgentOS.
_knowledge_ready = False    #Flag che indica se la knowledge e' stata caricata in LanceDB. Viene impostato a True dopo il primo run, per evitare di ricaricare i documenti ad ogni run.
_phase_docs_loaded = set()  #Set di documenti di fase già caricati

#Dizionario che mappa la fase di lockdown al nome del documento di consigli per quella fase.
#Utilizzato per caricare i documenti in LanceDB
#in pratica, vado ad associare la fase pandemica ai documenti che devono essere caricati in lanceDB
PHASE_DOC = {
    1: "consigli-lockdown-fase1.md",
    2: "consigli-lockdown-fase2.md",
    3: "consigli-lockdown-fase3.md",
}

#Funzioni per la lettura dei file di documentazione, per caricare la knowledge in LanceDB e per creare l'agente LLM Gemini + LanceDB al primo run.
def _docs_dir() -> Path:
    return Path(__file__).parent / "docs"
def _read_doc(name: str) -> str:   #lettura di un file 
    path = _docs_dir() / name
    if not path.exists():   #controlllo se il file esiste 
        return ""     #se non esiste, stringa vuota per non crashare
    return path.read_text(encoding="utf-8")   #UTF-8 per leggere cartteri accentati 

#Funzione che crea l'agente LLM Gemini + LanceDB al primo run della simulazione o di AgentOS. Restituisce l'istanza dell'agente.
#Utilizza il pattern Lazy singleton, l'agente viene creato solo al primo run e poi riutilizzato. La knowledge viene caricata in LanceDB solo al primo run, per evitare di ricaricare i documenti ad ogni run.
def _get_agno_agent():   #si crea una sola istanza globale dell'agente, che viene poi riutilizzata
    global _agno_agent, _knowledge_ready

    #Se l'agente e' gia' stato creato, restituisci l'istanza esistente
    if _agno_agent is not None:    #se l'agente esiste già, lo restituisco senza ricrearlo 
        return _agno_agent

    #Lazy import per evitare di caricare agno e Gemini se non necessario
    #il caricamento della libreria Agno e il collegamento a Gemini ha un costo
    #per evitare spreco di risorse, rimando questo caricamento al momento in cui serve davvero
    #non lo metto all'inizio del codice perchè potrei avere asi in cui l'agente non viene utilizzato
    from agno.agent import Agent
    from agno.db.sqlite import SqliteDb
    from agno.knowledge.embedder.google import GeminiEmbedder
    from agno.knowledge.knowledge import Knowledge
    from agno.learn import LearningMachine, LearningMode, UserMemoryConfig, UserProfileConfig
    from agno.models.google import Gemini
    from agno.vectordb.lancedb import LanceDb, SearchType
    from .llm_tools import (
        get_city_infection_rate,
        get_hospital_status,
        get_open_places,
        get_personal_status,
        get_yesterday_outcome,
    )

    #Creo la cartella tmp per LanceDB e SqliteDb, se non esiste per Agno
    tmp = Path("tmp")
    tmp.mkdir(parents=True, exist_ok=True)

    #Salvataggio dei documenti di conoscenza in LanceDB trasformando i file markdown in vettori embedding con GeminiEmbedder
    #GeminiEmbedder utilizza il modello Gemini per trasformare il testo in numeri vettoriali per la ricerca semantica.
    #La knowledge viene caricata solo al primo run, per evitare di ricaricare i documenti ad ogni run.
    knowledge = Knowledge(
        vector_db=LanceDb(
            table_name="citizen_knowledge",
            uri="tmp/lancedb",   #percorso per il salvataggio dei dati
            search_type=SearchType.vector,   #la ricera viene basata su similarità vettoriali
            embedder=GeminiEmbedder(),  #collego Gemini come motore di traduzione testo -> vettore
        ),
    )
    if not _knowledge_ready:   #se non è ancora stata cariata la knowledge
        for name in ("consigli-cittadino.md", "protocollo-citta.md", "fonti-covid.md"):
            knowledge.insert(path=str(_docs_dir() / name))  #inserimento documenti inziali 
        _knowledge_ready = True    #knowledge caricata
    #questa è una doppia protezione, per far si che non vengano cariati gli stessi documenti 2 volte

    #Database SqliteDb dove l'agente LLM salva lo storico delle conversazioni e delle run
    db = SqliteDb(db_file="tmp/citizen.db")

    #Creazione dell'agente LLM Gemini + LanceDB con tool, schema, memoria e RAG. 
    #L'agente e' un cittadino giovane che decide il proprio comportamento quotidiano in una citta' in epidemia
    #Usa i tool per leggere lo stato della citta', dell'ospedale, dei luoghi pubblici e del proprio stato di salute.
    _agno_agent = Agent(
        name="Truman",
        description="Un abitante giovane che decide il proprio giorno in una citta' in epidemia.",
        model=Gemini(id=config.GEMINI_MODEL),  #il nome esatto del modello usato è in config.py
        db=db,   #collegamento database
        instructions=[
            #System prompt per l'agente, definendo il comportamento, personalita e quando utilizzare i tool
            #Vincolo hard sono regole che l'agente deve rispettare
            "Sei UN cittadino giovane.",
            "Non sei contrario al vaccino. Decidi solo il tuo comportamento di oggi.",
            "Usa i tool per leggere salute, citta', ospedale, luoghi aperti e ieri.",
            "Consulta la knowledge: indicazioni OMS/Ministero e documenti di fase.",
            "Vincoli HARD: infetto => niente bar/supermercato affollato;",
            "ospedale saturo + grave => casa.",
            "Anche se non sei grave, se sei malato e l'ospedale ha posti liberi puoi valutare "
            "di andarci per farti controllare e curarti meglio: non e' obbligatorio, dipende "
            "da quanto ti senti a rischio e da quanto ti preoccupano i sintomi.",
            "Il centro vaccinale esiste solo se i tool dicono che e' aperto (fase 3).",
            "Se ieri ti sei ammalato dopo essere uscito, abbassa rischio e socialita'.",
            "Nel campo reason, scrivi come un'annotazione personale in prima persona: varia parole, "
            "struttura e tono rispetto alle motivazioni date nei giorni precedenti, anche quando la "
            "decisione di oggi e' simile a ieri.",
            "Evita frasi fatte ripetute uguali di giorno in giorno; racconta il motivo specifico di oggi.",
            "Rispondi solo con l'oggetto DailyPolicy richiesto.",
        ],
        tools=[
            #I tool di lettura (descritti in llm_tools.py)
            get_personal_status,
            get_city_infection_rate,
            get_hospital_status,
            get_open_places,
            get_yesterday_outcome,
        ],

        #Permette all'agente di fare ricerche nella knowledge per prendere decisioni sulla policy quotidiana quando lo ritiene utile
        knowledge=knowledge,  #collegamento knowledge 
        search_knowledge=True,   #attivazione RAG (decisioni potenziate dall conoscenza)

        #Forza la risposta finale e rispettare lo schema DailyPolicy, con validazione dei valori tramite pydantic
        output_schema=DailyPolicy,   #comunico ad Agno di forzre l'output al fomrato stabilito
        use_json_mode=True,    #uso la modalità JSON nativa delle API di Gemini

        #L'agente LLM costruire un profilo e una memoria del cittadino nel tempo e li aggiunge al contesto delle chiamate future
        #creo un oggetto LearningMachine per la momoria a lungo termine
        #UserProfileConfig, UserMemoryConfig sono funzioni native di Agno
        learning=LearningMachine(   
            user_profile=UserProfileConfig(mode=LearningMode.AGENTIC),  #gestione profilo agente
            user_memory=UserMemoryConfig(mode=LearningMode.AGENTIC),  #gestisce la memoria dell'agente
        ),  #la modalità AGENTIC permette al modello di decidere cosa salvare durante l'esecuzione
        add_learnings_to_context=True,  #funzione per aggiungere questa memoria alle chiamate future
        #impostando a True, il sistema prende le informazioni salvate nel profilo e nella memoria
        # e le inserisce nel contesto (prompt) della nuova chiamata a Gemini

        #Include le ultime 6 run nella memoria dell'agente per contestualizzare le decisioni odierne, utile per la coerenza del comportamento
        add_history_to_context=True,
        num_history_runs=6,

        #LLM formatta la risposta non in markdown ma in testo semplice per evitare problemi di parsing e validazione dello schema DailyPolicy
        markdown=False,
    )
    return _agno_agent

#Funzione che carica i documenti di fase in LanceDB per l'agente LLM, man mano che la simulazione avanza nelle fasi di lockdown.
#questa funzione viene chiamata quando si avanza nelle fasi pandemiche per aggiungere informazioni
def unlock_phase_knowledge(phase: int):
    agent = None
    for p in range(1, phase + 1):  #garantisce che, anche se si salta da es fase 0 a 3, vengano 
        #caricati tutti i documenti delle fasi intermedie, non solo quello della fase attuale
        #phase + 1 perchè, in range, l'estremo superiore è escluso dal conteggio
        name = PHASE_DOC.get(p)   #restituisce il nome del documento per quella fase
        if not name or name in _phase_docs_loaded:   #se il nome non esiste o è già stato caricato
            continue    #si salta alla fase sucessiva 
        if agent is None:   #se c'è un documento nuovo da caricare
            agent = _get_agno_agent()   #recupero l'istanza dell'agente (la crea se non esiste)
        agent.knowledge.insert(path=str(_docs_dir() / name))
        #si inseriesce il documento nella knowledge
        _phase_docs_loaded.add(name)   #si segna che il docmento è stato caricato (per non caricarlo 2 volte)

#Funzione che riconosce un payload di errore
def _is_error_payload(d) -> bool:
    return isinstance(d, dict) and "error" in d and "sociability_today" not in d
#controllo se il playload è davvero di errore (non contiene la sociability)
#o se è un playload normale che contiene la parola "error"

#Funzione che analizza la risposta di Gemini e la converte in un dizionario DailyPolicy valido
def _parse_policy(content) -> dict:
    #Quando la risposta di Gemini contiene un errore, solleva un'eccezione per interrompere la simulazione e segnalare il problema
    data = None
    if isinstance(content, DailyPolicy):  #se Agno ha già validato la risposta e restituito un istana di DailyPolicy
        data = content.model_dump()   #con model_dump() si converte l'oggetto valido in un dizionario per il codice
    elif isinstance(content, dict):   #content è già un dizionario (non ancora validato come oggetto DailyPolicy)
        if _is_error_payload(content):  #controllo se è un playload di errore
            raise ValueError(f"Gemini ha risposto con un errore: {content}")   #eccezione
        data = DailyPolicy(**content).model_dump()  #se è un dizionario valido
        #lo valido con DailyPolicy(**content) (specchetto il dizionario nelle sue chiavi e le valido)
        #dopo averlo validato, lo riconverto in dizionario con model_dump() 
    elif isinstance(content, str):    #se content è una semplice stringa di testo
        match = re.search(r"\{.*\}", content, re.DOTALL)   #estraggo la parte tra due { } (isolo la parte JSON)
        if match:   #se si trova un pezzo JSON nella stringa 
            parsed = json.loads(match.group(0))   #si converte il JSON in dizionario
            if _is_error_payload(parsed):   #controllo di errore
                raise ValueError(f"Gemini ha risposto con un errore: {parsed}")
            data = DailyPolicy(**parsed).model_dump() #validazione 
    if data is None:  #se non è stato prodotto un dato riconoscibile, si solleva un eccezione
        raise ValueError(f"Risposta di Gemini non interpretabile come DailyPolicy: {content!r}")

    #ultimo controllo di validazione (non eseguito in automatico da Pydantic)   
    #se il luogo di destinazione non è tra quelli consentiti, lo imposta ad "home"
    if data.get("intended_place") not in ("home", "grocery", "social", "hospital", "vaccine"):
        data["intended_place"] = "home"
    return data


#Quando Gemini non risponde, fallback policy prudente per evitare di far crashare la simulazione. Restituisce una policy con valori conservativi e un motivo di fallback.
def _fallback_policy(reason: str) -> dict:
    return {
        "sociability_today": 0.05,
        "wants_vaccine": False,
        "risk_tolerance": 0.1,
        "intended_place": "home",
        "reason": f"[fallback] {reason}",
    }    #valori prestabiliti per evitare crash del codice in caso di mancata risposta da Gemini

#L'agente non si accorge di essere entrato in incubazione (stato E): per lui e' come essere ancora
#sano (S). Il virus viene comunque registrato/simulato normalmente (vedi agent.update_health), ma
#questa "percezione" e' usata solo per decidere se serve chiamare Gemini: S->E non conta come un
#cambiamento notato dal cittadino, mentre E->I (comparsa dei sintomi) si'.
def _perceived_health_state(state):
    return config.S if state == config.E else state


#Funzione che decide se l'agente LLM deve ricalcolare la policy quotidiana, basandosi sul giorno corrente, lo stato dell'agente e della citta'.
def should_refresh_policy(agent: LLMAgent, day: int) -> bool:
    #se non è anocra stata presa una decisione fino ad ora (last_policy_day==None)
    #sarà necessaria una prima decisione (si restituisce True)
    last = getattr(agent, "last_policy_day", None)
    if last is None:
        return True
    perceived_now = _perceived_health_state(agent.state)  #recupero lo stato di salute percepito
    #recupero lo stato percepito all'ultima decisone dell'agente 
    perceived_last = _perceived_health_state(getattr(agent, "state_at_last_policy", agent.state))
    if perceived_now != perceived_last:    #se i due stati sono diversi, l'agente deve effettuare una nuova decisione
        return True
    model = getattr(agent, "model_ref", None) 
    last_phase = getattr(agent, "phase_at_last_policy", None)
    #verifico se la fase di lockdown è cambiata rispetto all'ultima decisione
    if model is not None and model.lockdown_phase != last_phase:
        return True
    #verifico se nel girono corrente è diventato disponibile il centro vaccinale (necessaria nuova decisione)
    if model is not None and model.vaccine_opened_on_day is not None and day == model.vaccine_opened_on_day:
        return True
    #verifico anche se non sono passati troppi gironi dall'ultima spesa dell'agente
    days_since_grocery = day - getattr(agent, "last_grocery_day", 0)
    #already_notified = getattr(agent, "grocery_reminder_sent", False)  #MODIFICA EFFETTUATA

    if days_since_grocery >= config.CITIZEN_GROCERY_REMINDER_DAYS:
    #if days_since_grocery >= config.CITIZEN_GROCERY_REMINDER_DAYS and not already_notified:
        return True
    return (day - last) >= config.LLM_DECIDE_EVERY_N_DAYS
#se nessuna delle altre condizioni e verà, controllo se sono passati un numero minimo di giorni 
#per efettuare una nuova decisione (nel codice sono stati impostati a 5 giorni per decisione)


#Funzione di ingresso chiamato dal resto della simulazione per ottenere la policy quotidiana dell'agente LLM. Restituisce un dizionario DailyPolicy valido.
#ogni giorno, verrà richiamata questa funzione per sapere la policy dell'agente
#decide se serve effettuare una chimaat a Gemini o si può riciclare la decisione del giorno prima
def fetch_daily_policy(agent: LLMAgent, day: int) -> dict:
    model = agent.model_ref
    set_active_world(model, agent)    #registra l'istanza attuale della simulazione
    snapshot = build_snapshot(model, agent, day)  #stato attuale della simulazione

    #Se non serve chiamare l'agente LLM per ricalcolare la policy, riutilizza la policy memorizzata nell'agente e aggiunge un motivo di riuso cache.
    #verifico se si deve decidere una nuova policy e se ne esiste già una salvata
    if not should_refresh_policy(agent, day) and getattr(agent, "daily_policy", None):
        cached = dict(agent.daily_policy)  #crea una copia della policy già salvata (non uso l'originale)
        cached["reason"] = (cached.get("reason") or "") + " [riuso cache]"
        #aggiungo una motivazione (riuso cache) e restituisco la policy (dizionario)
        return cached
    #Se serve ricalcolare la policy, costruisce un messaggio con lo snapshot della citta' e del cittadino osservato, insieme alle indicazioni per la fase di lockdown corrente.
    phase = snapshot["lockdown_phase"]    #recupero fase pandemica
    phase_name = PHASE_DOC.get(phase)    #recupero documento per la fse pandemica
    phase_text = _read_doc(phase_name) if phase_name else ""    #leggo documento se esiste
    if len(phase_text) > 1800:     #se il documento è troppo lungo (più di 1800 caratteri), lo taglio
        phase_text = phase_text[:1800] + "\n..."  #limito la lunghezza del prompt verso Gemini

    days_since_grocery = day - getattr(agent, "last_grocery_day", 0)
    grocery_note = (
        f"Non fai la spesa da {days_since_grocery} giorni: le scorte di casa si stanno esaurendo. "
        if days_since_grocery >= config.CITIZEN_GROCERY_REMINDER_DAYS
        else ""
    )   #nota da inserire nel messaggio per indicare i giorni passati dall'ultima spesa

    message = (     #prompt da inviare a gemini
        f"Scenario {snapshot['scenario']}. Giorno {day}. "
        f"Fase lockdown={phase}. "
        f"Sei il cittadino {snapshot['citizen_id']}, {snapshot['age']} anni, "
        f"{snapshot['personality']}, gruppo routine {snapshot['schedule_offset']}. "
        f"Salute={snapshot['health']} vaccinato={snapshot['vaccinated']} "
        f"grave={snapshot['severe']}. "
        f"Infetti in citta': {snapshot['infected_count']}/{snapshot['population']} "
        f"({snapshot['infection_rate']:.0%}). "
        f"Ospedale {snapshot['hospital_occupants']}/{snapshot['hospital_capacity']}"
        f"{' SATURO' if snapshot['hospital_full'] else ''}. "
        f"Vaccini aperti={snapshot['vaccine_open']}. "
        f"Coprifuoco alle {snapshot['curfew_hour']}. "
        f"Ieri: {snapshot['yesterday']}. "
        f"{grocery_note}"
        "Usa i tool se ti serve confermare, poi decidi la policy di oggi.\n\n"
        f"Indicazioni per questa fase (documentazione COVID):\n{phase_text}"
    )

    #Ritentazione con backoof in caso di errore di Gemini, per evitare che la simulazione si blocchi se Gemini non risponde.
    max_retries = 3   # Se dopo 3 tentativi Gemini resta irraggiungibile, si usa una policy di fallback prudente.
    last_err = None
    for attempt in range(max_retries):
        try:
            #Chiamata all'agente LLM per ottenere la policy quotidiana
            response = _get_agno_agent().run(input=message, session_id=config.SESSION_ID, user_id=config.USER_ID,)
            #Risposta della chiamata
            policy = _parse_policy(response.content)  #se la chiamat ha successo, response.content contiene la risposta
            #Aggiornamento e ritorno della policy
            agent.phase_at_last_policy = phase
            #agent.grocery_reminder_sent = (day - getattr(agent, "last_grocery_day", 0)) >= config.CITIZEN_GROCERY_REMINDER_DAYS
            return policy
        except Exception as exc:   #se si verifia un eccezione
            last_err = exc   #si slava l'errore
            if attempt < max_retries - 1:   #se non siamo ancora all'ultimo tentativo disponibile
                wait = 5 * (attempt + 1)   #calcola un tempo di attesa (backoff)
                print(f"[llm_agent] tentativo {attempt + 1}/{max_retries} fallito ({exc}); riprovo tra {wait}s")
                time.sleep(wait)    #attende

    print(f"[llm_agent] Gemini non disponibile dopo {max_retries} tentativi ({last_err}); uso fallback prudente.")
    agent.phase_at_last_policy = phase   #se Gemini non risponde, si usa la policy di fallback
    #agent.grocery_reminder_sent = (day - getattr(agent, "last_grocery_day", 0)) >= config.CITIZEN_GROCERY_REMINDER_DAYS
    return _fallback_policy(str(last_err))  #include l'ultimo errore nella motivazione 

def get_citizen_agent():
    return _get_agno_agent()