---
name: recipe-substitutions
description: Regole per sostituire ingredienti nelle ricette quando l'utente ha allergie, intolleranze o ingredienti mancanti.
metadata:
  version: "1.0.0"
  tags: ["cucina", "sostituzioni", "allergie"]
---

# Recipe Substitutions

Usa questa skill quando l'utente segnala un'allergia, un'intolleranza,
o chiede esplicitamente come sostituire un ingrediente in una ricetta.

## Quando usarla

- L'utente menziona allergie o intolleranze: noci, glutine, lattosio.
- L'utente chiede "posso sostituire X?"
- Un ingrediente di una ricetta proposta non e' disponibile.

## Categorie principali

- Latticini: latte -> bevanda di soia, mandorla o avena.
- Glutine: farina di grano -> mix gluten-free, farina di riso o farina di mandorle.
- Uova: uovo -> semi di lino con acqua, aquafaba o banana matura.
- Frutta secca: noci o mandorle -> semi di girasole o semi di zucca.

## Linee guida

- Sostituire 1:1 in massa quando possibile.
- Avvertire se consistenza o sapore cambiano in modo significativo.
- Per allergie severe, raccomandare sempre di verificare le etichette
  dei prodotti sostitutivi.
- Non proporre sostituti che appartengono alla stessa famiglia allergenica
  se l'utente dichiara un'allergia severa.

## Script disponibili

- `find_substitute.py`: dato `ingredient` e `constraint`, ritorna il
  sostituto consigliato come stringa. Lo script vive in `scripts/`, ma il
  tool Agno `get_skill_script` lo richiama con `script_path="find_substitute.py"`.
  Puoi passare gli argomenti come JSON singolo
  `{"ingredient":"latte","constraint":"lattosio"}`, come due argomenti
  posizionali `latte`, `lattosio`, oppure in stile CLI:
  `--ingredient latte --constraint lattosio`.
