#Punti di interesse, rappresentano regioni della mappa con regole di accesso, orari di apertura e capienza massima.

from .city import cells_with_char
from .config import HOSPITAL_CAPACITY, VACCINE_START_DAY


class PointOfInterest:
    def __init__(self, name, char, open_hour=0, close_hour=24,
                 open_from_day=0, capacity=None, restricted_to=None):   #valori di default
        self.name = name    #nome del punto di interesse
        self.char = char    #lettera con cui verrà definito nella mappa

        #La regione del POI è l'insieme di tutte le celle della mappa con lo stesso carattere
        self.cells = set(cells_with_char(char))  
        if not self.cells:
            raise ValueError(f"Nessuna cella con carattere '{char}' trovata per il POI '{name}'")

        #estraggo tutte le coordinate x ed y che compongono il POI
        xs = [c[0] for c in self.cells]
        ys = [c[1] for c in self.cells]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)
        #Centro geometrico dell'area utilizzato solo per etichette e annotazioni
        self.pos = ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

        self.open_hour = open_hour          #Ora di apertura
        self.close_hour = close_hour        #Ora di chiusura
        self.open_from_day = open_from_day  #Giorno a partire dal quale il POI è aperto
        self.capacity = capacity            #Capienza massima (Se none è illmitata)
        self.restricted_to = restricted_to  #Condizione di accesso (True se può entrare)
        self.occupants = []                 #Agenti attualmente presenti nel POI (solo per ospedale e centro vaccinale)

    #Verifica se il POI è aperto in un dato giorno e ora
    def is_open(self, hour, day):
        return (self.open_hour <= hour < self.close_hour) and (day >= self.open_from_day)

    #Verifica se il POI ha ancora spazio per nuovi agenti (solo per ospedale e centro vaccinale)
    def has_room(self):
        return self.capacity is None or len(self.occupants) < self.capacity

    #Verifica se un agente può entrare nel POI in base alle regole di accesso e alla capienza
    def can_accept(self, agent):
        if self.restricted_to is not None and not self.restricted_to(agent):
            return False
        return self.has_room()   #si verifica se si ci sono stanze disponibili

    #Verifica se una posizione (cella) fa parte fisicamente del POI
    #usa es. in HOSPITAL.contains(agent.pos) per sapere se l'agente si trova nell'area dell'ospedale
    def contains(self, pos):
        return pos in self.cells

    #Registra l'ingresso di un agente tra gli occupanti.
    def admit(self, agent):
        self.occupants.append(agent)

    #Rimuove un agente dagli occupanti (dimissione/uscita), se presente e decrementa il conteggio di chi occupa il POI
    def discharge(self, agent):
        if agent in self.occupants:
            self.occupants.remove(agent)

    #Calcola il rapporto tra il numero di agenti presenti e la capienza massima del POI 
    # (solo per ospedale e centro vaccinale)
    #usato per colorare il riempimento delle strutture
    def fill_ratio(self):
        if self.capacity is None:   #nessuna capienza definita
            return 0.0
        return len(self.occupants) / self.capacity

#Definizione dei POI specifici della simulazione
#BAR
BAR = PointOfInterest(
    "Bar", 
    "b", 
    open_hour=6, 
    close_hour=23
)

#CENTRO COMMERCIALE
# Usato come supermercato / spesa (una volta ogni N giorni, vedi routines.py).
MALL = PointOfInterest(
    "Supermercato",
    "c",
    open_hour=9,
    close_hour=20
)

#OSPEDALE
HOSPITAL = PointOfInterest(
    "Ospedale",
    "h",
    capacity=HOSPITAL_CAPACITY,
)

#CENTRO VACCINALE
VACCINE_CENTER = PointOfInterest(
    "Centro Vaccinale", 
    "v",
    open_hour=8, 
    close_hour=18,
    open_from_day=VACCINE_START_DAY,
    restricted_to=lambda agent: not agent.novax and not agent.vaccinated and agent.state != "I"
)

#PARCO
PARCO = PointOfInterest("Parco", "p")


SOCIAL_POIS = [BAR, MALL, PARCO]
ALL_POIS = [BAR, MALL, HOSPITAL, VACCINE_CENTER, PARCO]
