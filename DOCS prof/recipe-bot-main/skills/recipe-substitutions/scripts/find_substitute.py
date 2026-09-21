#!/usr/bin/env python3
"""Trova un sostituto per un ingrediente dato un vincolo."""

import json
import sys


SUBSTITUTIONS = {
    ("latte", "lattosio"): "latte delattosato o bevanda di soia/mandorla",
    ("latte", "vegano"): "bevanda di soia, mandorla o avena",
    ("uova", "vegano"): "1 uovo = 1 cucchiaio di semi di lino + 3 cucchiai di acqua",
    ("noci", "allergia"): "semi di girasole o semi di zucca",
    ("burro", "vegano"): "olio di cocco o margarina vegetale",
    ("farina", "glutine"): "mix gluten-free o farina di riso",
}


CONSTRAINT_ALIASES = {
    "intolleranza al lattosio": "lattosio",
    "intolleranza lattosio": "lattosio",
    "intollerante al lattosio": "lattosio",
    "intollerante lattosio": "lattosio",
    "senza lattosio": "lattosio",
    "allergia alle noci": "allergia",
    "allergico alle noci": "allergia",
    "allergica alle noci": "allergia",
    "senza glutine": "glutine",
    "celiachia": "glutine",
}


def parse_args(argv: list[str]) -> tuple[str, str]:
    """Accetta JSON, flag CLI o due argomenti posizionali."""
    if not argv:
        return "", ""

    if "--ingredient" in argv:
        ingredient = value_after_flag(argv, "--ingredient")
        constraint = value_after_flag(argv, "--constraint")
        return ingredient, constraint

    if len(argv) == 1:
        try:
            data = json.loads(argv[0])
        except json.JSONDecodeError:
            return argv[0], ""

        if isinstance(data, dict):
            return data.get("ingredient", ""), data.get("constraint", "")
        if isinstance(data, list) and len(data) >= 2:
            return str(data[0]), str(data[1])

    return argv[0], argv[1] if len(argv) > 1 else ""


def value_after_flag(argv: list[str], flag: str) -> str:
    if flag not in argv:
        return ""

    value_index = argv.index(flag) + 1
    values = []
    while value_index < len(argv) and not argv[value_index].startswith("--"):
        values.append(argv[value_index])
        value_index += 1
    return " ".join(values)


def find_sub(ingredient: str, constraint: str) -> str:
    ingredient_key = ingredient.lower().strip()
    constraint_key = constraint.lower().strip()
    constraint_key = CONSTRAINT_ALIASES.get(constraint_key, constraint_key)
    key = (ingredient_key, constraint_key)
    return SUBSTITUTIONS.get(
        key,
        f"Nessun sostituto noto per {ingredient!r} con vincolo {constraint!r}.",
    )


if __name__ == "__main__":
    ingredient, constraint = parse_args(sys.argv[1:])
    print(find_sub(ingredient, constraint))
