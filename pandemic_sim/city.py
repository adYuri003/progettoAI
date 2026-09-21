from collections import deque

#La città è una mappa formata da una griglia di celle, con strade ed edifici, ogni carattere è una cella:
# "." strada
# "#" edificio residenziale (casa)
# "_" cella non percorribile
# "c" centro commerciale
# "h" ospedale
# "p" parco
# "b" bar
# "v" centro vaccinale
CITY_MAP = [
    "____________________________________________________",
    "____________________________________________________",
    "_cccccccccccccccccccccc____vvvvv_____hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc____vvvvv_____hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc____vvvvv_____hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc____vvvvv_____hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc____vvvvv_____hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc_____...______hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc............._hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc............._hhhhhhhhhhhhhh_",
    "_cccccccccccccccccccccc.............-hhhhhhhhhhhhhh_",
    "__________..___________..............hhhhhhhhhhhhhh_",
    "____................................_hhhhhhhhhhhhhh_",
    "____................................_hhhhhhhhhhhhhh_",
    "____..............................................._",
    "____..............................................._",
    "____..________.._________......__________...._______",
    "_###..###__###..###______......______pppppppppppp___",
    "____..________.._________......______pppppppppppp___",
    "_###..###__###..###______......______pppppppppppp___",
    "____..________..___________..________pppppppppppp___",
    "_###..###__###..###______bbbbbb______pppppppppppp___",
    "____..________.._________bbbbbb______pppppppppppp___",
    "_###..###__###..###______bbbbbb______pppppppppppp___",
    "____..________.._________bbbbbb______pppppppppppp___",
    "_###..###__###..###______bbbbbb______pppppppppppp___",
    "____..________.._________bbbbbb______pppppppppppp___",
    "_###..###__###..###______bbbbbb______pppppppppppp___",
    "____..________.._________bbbbbb______pppppppppppp___",
    "_###..###__###..###______bbbbbb______pppppppppppp___",
    "____________________________________________________",
]

CITY_MAP = list(reversed(CITY_MAP))   #reversed per non far renderizzare al codice la mappa al contrario

GRID_W = len(CITY_MAP[0])   # larghezza (colonne)
GRID_H = len(CITY_MAP)      # altezza (righe)


#Celle percorribili apparte l'ospedale dove possono entrare solo gli agenti autorizzati (ricoverati o pazienti gravi)
def is_street(x, y, allow_hospital=False):   #per stabilire dove un agente può camminare
    ch = CITY_MAP[y][x]    #recupera il carattere nella posizione specifica
    if ch == "h":   #se la cella appartiene all'ospedale, il cittadino dev'essere atutorizzato
        return allow_hospital   #verifia se il cittadino è autorizzato
    return ch in (".", "#", "c", "p", "b", "v")
#per le altre celle, si verifica solo se il carattere è tra quell percorribili

#Tutte le celle della mappa che hanno il carattere `ch`
def cells_with_char(ch):   #funzione che raggruppa tutte le celle di uno stesso tipo 
    return [(x, y) for y in range(GRID_H) for x in range(GRID_W) if CITY_MAP[y][x] == ch]

# Solo le celle abitative (case), usate come "casa" per gli agenti
HOME_CELLS = cells_with_char("#")   #recupera tutte le celle con carattere "#"

#non include le celle dell'ospedale 
STREET_CELLS = [(x, y) for y in range(GRID_H) for x in range(GRID_W)
                if is_street(x, y)]   
#costruisce la lista di tutte le celle percorribili normalemente nella mappa

#Funzione che calcola il percorso più breve tra una cella di partenza e una meta usando BFS (Breadth First Search).
#Il "goal" è il punto di arrivo, che può essere una singola cella o un insieme di celle (come tutte le celle di un POI).
#Allow_hospital indica se l'agente può attraversare l'area dell'ospedale o meno.
#Ritorna il punto di partenza alla meta effettivamente raggiunta
#BFS è l'algoritmo standard per trovare il cammino più breve in una griglia dove ogni passo ha lo stesso costo
def bfs_path(start, goal, allow_hospital=False):  #calcola il percorso più breve tra 2 punti
    if isinstance(goal, (set, frozenset, list)):
        goal_cells = set(goal)    #la destinazione può essere un singolo punto 
    else:
        goal_cells = {goal}    #oppure la destinazione può essere una lista di punti accessibili

    if start in goal_cells:   #se l'agente si trova già nella destinazione, non si muove (lista vuota)
        return []

# FS funziona ad "onde concentriche", per farlo usa una coda (queue):
# l'agente esamina prima tutte le caselle distanti 1 passo, 
# poi tutte quelle distanti 2 passi e così via
    visited = {start}   #tiene traccia delle caselle già calcolate (per evitare di rifare le stesse caselle)
    queue = deque([(start, [])])   #contiene la casella attuale e la lsita di passi fatti per arrivarci

    while queue:
        (x, y), path = queue.popleft() #prendo la casella più "vecchia" nella lista (dove si trova l'agente)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):  #analizzo le 4 direzioni adicenti (su, giù, destra, sinistra)
            nx, ny = x + dx, y + dy  #calcolo le coordinate della casella visitata

            #verifico se non sto uscendo dalla mappa o non sono nell'ospedale senza permesso
            if 0 <= nx < GRID_W and 0 <= ny < GRID_H and is_street(nx, ny, allow_hospital=allow_hospital):
                #controllo se la tabella non è già stata visitata (altrimenti la ignoro)
                if (nx, ny) not in visited:
                    new_path = path + [(nx, ny)]  #aggiungo la casella al percorso fatto
                    if (nx, ny) in goal_cells:   #se la casella è nella destinazione
                        return new_path   #restituisco il percorso costruito
                    visited.add((nx, ny))   #aggiungo la tabella tra quelle visitate
                    queue.append(((nx, ny), new_path))   #aggiungo la casella nella queue
    return []
