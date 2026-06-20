from __future__ import annotations
import re
from typing import Optional

# --------------------------------------------------------------------------- #
#  Number-word parsing
# --------------------------------------------------------------------------- #
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_VAGUE = {"several", "many", "multiple", "numerous", "scores", "dozens",
          "few", "some", "handful", "countless"}
_FIXED = {"a": 1, "an": 1, "couple": 2, "dozen": 12}

_NUM_WORD = (
    r"\d{1,4}"
    r"|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?"
    r"|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|several|many|multiple|numerous|scores|dozens|few|some|handful|countless"
    r"|a|an|couple|dozen"
)


def parse_quantity(text: str) -> Optional[int]:
    """Convert a quantity expression to an int; None when genuinely vague."""
    if text is None:
        return None
    t = text.strip().lower().replace("-", " ")
    t = re.sub(r"\bof\b", " ", t).strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    words = t.split()
    if len(words) == 2 and words[0] in ("a", "an") and words[1] in _FIXED:
        return _FIXED[words[1]]
    if t in _VAGUE:
        return None
    if t in _FIXED:
        return _FIXED[t]
    if t in _ONES:
        return _ONES[t]
    if t in _TENS:
        return _TENS[t]
    if len(words) == 2 and words[0] in _TENS and words[1] in _ONES and _ONES[words[1]] < 10:
        return _TENS[words[0]] + _ONES[words[1]]
    return None


# --------------------------------------------------------------------------- #
#  Affiliation classification
# --------------------------------------------------------------------------- #
_AFFILIATION_LEXICON = {
    "militant": {"militant", "militants", "terrorist", "terrorists", "insurgent",
                 "insurgents", "rebel", "rebels", "ultra", "ultras", "cadre", "cadres",
                 "guerrilla", "guerrillas", "fidayeen", "gunman", "gunmen", "attacker",
                 "attackers", "infiltrator", "infiltrators"},
    "security": {"soldier", "soldiers", "jawan", "jawans", "trooper", "troopers",
                 "army", "policeman", "policemen", "cop", "cops", "constable",
                 "constables", "personnel", "paramilitary", "crpf", "bsf", "ssb",
                 "cisf", "forces", "officer", "officers", "commando", "commandos",
                 "guard", "guards", "spo", "spos"},
    "civilian": {"civilian", "civilians", "villager", "villagers", "worker", "workers",
                 "labourer", "labourers", "laborer", "laborers", "driver", "drivers",
                 "resident", "residents", "protester", "protesters", "protestor",
                 "protestors", "student", "students", "pilgrim", "pilgrims",
                 "passenger", "passengers", "woman", "women", "man", "men", "child",
                 "children", "people", "youth"},
}
_TOKEN_AFFILIATION = {tok: aff for aff, toks in _AFFILIATION_LEXICON.items() for tok in toks}


def classify_affiliation(span: str) -> str:
    for tok in re.findall(r"[a-z]+", span.lower()):
        aff = _TOKEN_AFFILIATION.get(tok)
        if aff:
            return aff
    return "unspecified"


# --------------------------------------------------------------------------- #
#  Casualty extraction
# --------------------------------------------------------------------------- #
_KILLED_VERBS = (r"killed|dead|died|martyred|slain|neutralis(?:ed)?|neutraliz(?:ed)?|"
                 r"gunned\s+down|shot\s+dead|succumb(?:ed)?|lost\s+(?:their|his|her)\s+li(?:fe|ves)")
_INJURED_VERBS = r"injured|wounded|hurt|maimed"

_CASUALTY_RE = re.compile(
    rf"\b({_NUM_WORD})\b"
    rf"((?:\s+[A-Za-z][\w'-]*){{0,4}}?)\s+"
    rf"\b(?P<outcome>{_KILLED_VERBS}|{_INJURED_VERBS})\b",
    re.IGNORECASE,
)


def _is_killed(outcome: str) -> bool:
    o = outcome.lower()
    return not any(w in o for w in ("injur", "wound", "hurt", "maim"))

_SINGULAR_HUMAN = (
    r"soldier|jawan|trooper|policeman|cop|constable|commando|officer|guard|spo|"
    r"militant|terrorist|insurgent|rebel|gunman|cadre|ultra|infiltrator|"
    r"civilian|villager|worker|labourer|laborer|driver|resident|protester|"
    r"protestor|student|pilgrim|passenger|woman|man|child|youth|leader|person|"
    r"victim|farmer|teenager|boy|girl|minor|teacher|trader|shopkeeper"
)
_PASSIVE_FOLLOW = (
    r"in|during|by|near|after|while|on|at|over|amid|following|as|when|outside|"
    r"inside|along|and"
)
_NEG_NEAR = re.compile(
    r"\b(?:no|not|without|zero|never|nobody|none|avoid|prevent|prevented)\b",
    re.IGNORECASE,
)
_SINGULAR_RE = re.compile(
    rf"(?:\b(?:a|an|the|one)\s+)?\b(?P<noun>{_SINGULAR_HUMAN})\s+"
    rf"(?:was\s+|were\s+|been\s+|got\s+)?"
    rf"(?P<outcome>{_KILLED_VERBS}|{_INJURED_VERBS})\b"
    rf"(?=\s+(?:{_PASSIVE_FOLLOW})\b|\s*[.,;:])",
    re.IGNORECASE,
)
_BODIES_RE = re.compile(
    rf"\b(?P<num>{_NUM_WORD})\s+(?:dead\s+|decomposed\s+|mutilated\s+|charred\s+)?"
    rf"bodies\b(?:(?:\s+[A-Za-z][\w'-]*){{0,5}}?)\s+"
    rf"\b(?:found|recovered|retrieved|exhumed|handed\s+over)\b",
    re.IGNORECASE,
)

_OBJ_PERSON = (
    _SINGULAR_HUMAN +
    r"|soldiers|militants|civilians|people|persons|men|jawans|troopers|cops|police|"
    r"terrorists|insurgents|cadres|rebels|gunmen|villagers|protesters|protestors|"
    r"students|workers|residents|passengers"
)
_OBJ_AFTER = re.compile(
    rf"^\s+(?:{_NUM_WORD})\s+(?:[A-Za-z][\w'-]*\s+){{0,2}}?(?:{_OBJ_PERSON})\b",
    re.IGNORECASE,
)


def extract_casualties(text: str) -> dict:
    empty = {"killed": [], "injured": []}
    if not text:
        return empty
    raw_killed, raw_injured = [], []

    # Pass 1 -- number-anchored "<n> <noun> killed/injured"
    for m in _CASUALTY_RE.finditer(text):
        if _OBJ_AFTER.match(text[m.end():]):
            continue
        quant_raw = m.group(1)
        middle = m.group(2) or ""
        outcome = m.group("outcome")
        entry = {
            "count": parse_quantity(quant_raw),
            "raw": f"{quant_raw.strip()}{middle.rstrip()}".strip(),
            "affiliation": classify_affiliation(middle) if middle.strip() else "unspecified",
        }
        (raw_killed if _is_killed(outcome) else raw_injured).append(entry)

    # Pass 2 -- singular human victim, no number -> count 1
    for m in _SINGULAR_RE.finditer(text):
        if _NEG_NEAR.search(text[max(0, m.start() - 18):m.start()]):
            continue
        noun, outcome = m.group("noun"), m.group("outcome")
        entry = {"count": 1, "raw": noun.strip(), "affiliation": classify_affiliation(noun)}
        (raw_killed if _is_killed(outcome) else raw_injured).append(entry)

    # Pass 3 "<n> bodies found/recovered" -> killed
    for m in _BODIES_RE.finditer(text):
        num_raw = m.group("num")
        raw_killed.append({
            "count": parse_quantity(num_raw),
            "raw": f"{num_raw.strip()} bodies",
            "affiliation": "unspecified",
        })

    return {"killed": _reconcile(raw_killed), "injured": _reconcile(raw_injured)}


def _reconcile(entries: list) -> list:
    """Keep the largest known count per affiliation (avoids double counting)."""
    best: dict = {}
    for e in entries:
        aff = e["affiliation"]
        cur = best.get(aff)
        if cur is None:
            best[aff] = e
            continue
        cur_c = cur["count"] if cur["count"] is not None else -1
        new_c = e["count"] if e["count"] is not None else -1
        if new_c > cur_c:
            best[aff] = e
    return list(best.values())


def summarize_casualties(casualties: dict) -> dict:
    """Totals for scoring/fingerprinting. Vague counts (None) count as 1."""
    def _sum(items):
        return sum((it["count"] if it["count"] is not None else 1) for it in items)
    return {
        "total_killed": _sum(casualties.get("killed", [])),
        "total_injured": _sum(casualties.get("injured", [])),
        "has_casualties": bool(casualties.get("killed") or casualties.get("injured")),
    }


def format_casualties(casualties) -> str:
    """Human-readable one-liner. Accepts the dict schema or a legacy list."""
    if not casualties:
        return ""
    if isinstance(casualties, list):
        return ", ".join(str(x) for x in casualties)

    def _fmt(items):
        parts = []
        for it in items:
            if isinstance(it, str):
                parts.append(it)
                continue
            c = it.get("count")
            aff = it.get("affiliation", "unspecified")
            label = "" if aff == "unspecified" else f" {aff}"
            parts.append(f"{c if c is not None else 'several'}{label}")
        return ", ".join(parts)

    killed = _fmt(casualties.get("killed", []))
    injured = _fmt(casualties.get("injured", []))
    out = []
    if killed:
        out.append(f"Killed: {killed}")
    if injured:
        out.append(f"Injured: {injured}")
    return " | ".join(out)