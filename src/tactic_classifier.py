from __future__ import annotations
import re
from typing import Any, Optional

try:
    from src.config import BART_MODEL, BART_CONFIDENCE_THRESHOLD
except Exception:
    BART_MODEL = "facebook/bart-large-mnli"
    BART_CONFIDENCE_THRESHOLD = 0.50

# --------------------------------------------------------------------------- #
#  STAGE 1: coarse categories
# --------------------------------------------------------------------------- #
COARSE = {
    "VIOLENT": "a violent security incident such as a gunfight, bombing, ambush, killing, or armed attack",
    "UNREST":  "a protest, strike, blockade, riot, or civil unrest",
    "ROUTINE": "a routine civic, political, administrative, sports, or development matter",
}
HYPOTHESIS_TEMPLATE = "This news report is about {}."
COARSE_TO_INCIDENT = {"VIOLENT": "Kinetic", "UNREST": "Unrest", "ROUTINE": "Other"}

# --------------------------------------------------------------------------- #
#  STAGE 2: tactic keyword patterns, split by category.
# --------------------------------------------------------------------------- #
KINETIC_PATTERNS = [
    (r"\b(ieds?|bombs?|grenades?|explosives?|blasts?|explosions?|vbieds?|sticky bombs?)\b", "IED/Explosion"),
    (r"\b(encounters?|gunfights?|crossfires?|shootouts?|firefights?)\b", "Gunfight/Encounter"),
    (r"\b(ambush(?:es)?)\b", "Ambush"),
    (r"\b(assassinat\w+|targeted killings?|target killings?|snip\w+|shot dead|gunned down)\b", "Targeted Attack"),
    (r"\b(infiltration\w*|cross-?border|exfiltration)\b", "Border Infiltration"),
    (r"\b(caso|search operations?|cordon\w*|raids?|crackdowns?|seiz\w+|recover\w+|arrest\w+|bust\w+|recovered)\b", "Search Operation"),
]
UNREST_PATTERNS = [
    (r"\b(stone[- ]pelting|stone[- ]throwing)\b", "Stone Pelting"),
    (r"\b(arson|vandalism|torched?|set ablaze|set on fire)\b", "Arson/Vandalism"),
    (r"\b(protests?|riots?|curfews?|clash(?:es)?|economic blockades?|blockades?|bandhs?|hartals?|shutdowns?|strikes?|demonstrations?)\b", "Civil Unrest"),
]
_KIN = [(re.compile(p, re.IGNORECASE), t) for p, t in KINETIC_PATTERNS]
_UNR = [(re.compile(p, re.IGNORECASE), t) for p, t in UNREST_PATTERNS]

_NON_CONFLICT_BLACKLIST = [
    "cricket", "tournament", "match", "championship", "sports", "yoga",
    "festival", "jkssb", "verification", "exam", "paper leak", "result",
    "seminar", "conferred", "confers", "award", "golf", "hockey", "marathon",
    "panchayat", "voters", "tourism", "pageant", "cultural", "inaugurat",
    "foundation stone", "scholarship", "recruitment", "vacancy", "convocation",
]
_NEGATION_CUES = [
    "no ", "not ", "without any", "averted", "foiled", "thwarted",
    "prevented", "false alarm", "hoax", "ruled out",
]


def has_negation_cue(title: str) -> bool:
    t = (title or "").lower()
    return any(cue in t for cue in _NEGATION_CUES)


def is_blacklisted(title: str) -> bool:
    t = (title or "").lower()
    return any(term in t for term in _NON_CONFLICT_BLACKLIST)


# --------------------------------------------------------------------------- #
#  CIVIC CIRCUIT-BREAKER
# --------------------------------------------------------------------------- #
_HARD_VIOLENCE = [
    "killed", "killing", "gunfight", "gun battle", "gunbattle", "encounter",
    "blast", "explosion", "grenade", "ied", "opened fire", "open fire",
    "firing", "ambush", "fidayeen", "shootout", "shoot-out", "shot dead",
    "gunned down", "suicide attack", "car bomb", "sticky bomb", "mortar",
    "sniper", "abducted", "kidnapped", "lynched", "massacre", "martyred",
    "slain", "blown up", "hand grenade", "landmine",
]
_UNREST_KEYWORDS = [
    "protest", "bandh", "hartal", "shutdown", "blockade",
    "demonstration", "sit-in", "dharna", "gherao", "agitation",
]
_CIVIC_TERMS = [
    # legal / judicial
    "court", "bail", "verdict", "acquit", "sentenced", "hearing", "petition",
    "chargesheet", "charge sheet", "charge-sheet", "enquiry", "inquiry",
    "tribunal", "judicial", "judge", "nia case", "summons", "plea", "custody",
    "litigation",
    # medical / health
    "patient", "hospital", "gmc ", "medical college", "doctor", "treatment",
    "ailment", "illness", "surgery", "health department", "dialysis", "icu",
    # diplomacy / governance / administration
    "agreement", "agree ", "mou", "pact", " talks", "defer", "deferred",
    "summit", "delegation", "signed", "accord", "memorandum", "bilateral",
    "cabinet", "assembly session", "budget", "scheme", "portfolio",
    "sworn in", "oath", "by-election", "manifesto", "notification",
    "boundary talks", "border talks", "border dispute", "border row",
    # civic honours / culture / development / admin
    "chakra", "award", "conferred", "confers", "felicitat", "tournament",
    "trophy", "cultural", "festival", "inaugurat", "foundation stone",
    "scholarship", "recruitment", "convocation", "exhibition", "seminar",
    "workshop", "land row", "land dispute", "farmers", "political rivals",
]


def _hit(text: str, terms) -> bool:
    return any(term in text for term in terms)


def has_hard_violence(title: str, content: str = "") -> bool:
    text = f"{title or ''} {str(content or '')[:600]}".lower()
    return _hit(text, _HARD_VIOLENCE)


def civic_override(category: str, title: str, content: str = "") -> str:
    """Demote civic news BART mislabels as VIOLENT/UNREST -- unless a real
    violent-event word is present."""
    if category == "ROUTINE":
        return category
    head = (title or "").lower()
    if _hit(head, _HARD_VIOLENCE):
        return category 
    if _hit(head, _UNREST_KEYWORDS) and not _rank_tactics(title, "", _KIN):
        return "UNREST"
    if _hit(head, _CIVIC_TERMS) and not _rank_tactics(title, "", _KIN) \
            and not _rank_tactics(title, "", _UNR):
        return "ROUTINE"
    return category

_ACCIDENT_CONTEXT = [
    "accident",        # accident / accidental / accidentally / road accident
    "collision", "car-bus", "bus-truck", "overturn", "mishap", "capsize",
    "stampede", "drowned", "drowning", "electrocut", "cylinder blast",
    "gas leak", "building collapse", "wall collapse", "bridge collapse",
    "fell into", "fell from", "ferry capsiz", "boat capsiz", "lightning",
    "falls into", "falls from", "skid", "skidded", "swept away", "veers off", "veered off",
    "plunges into gorge", "plunged into gorge", "plunges into river", "plunged into river",
    "plunges into ravine", "plunged into ravine",
]
_HOSTILE_ACTION = [
    "militant", "terrorist", "insurgent", "fidayeen", "ambush", "attack",
    "gunfight", "encounter", "opened fire", "open fire", "shot dead",
    "gunned down", "infiltrat", "suicide", "grenade attack", "ied attack",
]

def accident_override(category: str, title: str, content: str = "") -> str:
    """§7 P4: road accidents / mishaps / accidental blasts that BART reads as
    VIOLENT are not conflict. Demote them to ROUTINE -- UNLESS the headline also
    carries a hostile-action word (so 'soldier killed in militant ambush, vehicle
    overturns' is never suppressed). Headline-only, like civic_override."""
    if category != "VIOLENT":
        return category
    head = (title or "").lower()
    if _hit(head, _ACCIDENT_CONTEXT) and not _hit(head, _HOSTILE_ACTION):
        return "ROUTINE"
    return category

def _rank_tactics(title: str, content: str, compiled) -> list:
    """Return [(granular, weighted_score), ...] sorted desc, only positives."""
    title_l = (title or "").lower()
    text_l = f"{title_l} {(content or '').lower()}"
    scores = {}
    order = {tac: i for i, (_, tac) in enumerate(compiled)}
    for rx, tac in compiled:
        s = 2.0 * len(rx.findall(title_l)) + 1.0 * len(rx.findall(text_l))
        if s > 0:
            scores[tac] = scores.get(tac, 0.0) + s
    return sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))


def has_any_tactic_signal(title: str) -> bool:
    return bool(_rank_tactics(title, "", _KIN) or _rank_tactics(title, "", _UNR))


def assign_tactic(category: str, title: str, content: str = "") -> dict:
    """Stage 2: given a coarse category, pick the specific tactic from keywords."""
    if category == "ROUTINE":
        return {"granular": "Other", "incident": "Other",
                "secondary": None, "tactic_uncertain": False}

    compiled = _KIN if category == "VIOLENT" else _UNR
    ranked = _rank_tactics(title, content, compiled)

    if ranked:
        granular = ranked[0][0]
        secondary = ranked[1][0] if len(ranked) > 1 else None
        return {"granular": granular, "incident": COARSE_TO_INCIDENT[category],
                "secondary": secondary, "tactic_uncertain": False}

    # flag for review
    generic = "Armed Incident" if category == "VIOLENT" else "Civil Unrest"
    return {"granular": generic, "incident": COARSE_TO_INCIDENT[category],
            "secondary": None, "tactic_uncertain": (category == "VIOLENT")}


def interpret_coarse(coarse_scores: dict, conf_threshold: float = BART_CONFIDENCE_THRESHOLD) -> tuple:
    """Pick the top coarse category; flag low confidence."""
    top = max(coarse_scores, key=lambda k: coarse_scores[k])
    conf = coarse_scores[top]
    return top, conf, (conf < conf_threshold)


def _result(granular, incident, confidence, secondary, needs_review, source, category):
    return {
        "granular_incident_type": granular,
        "incident_type": incident,
        "tactic_confidence": round(float(confidence), 4),
        "secondary_tactic": secondary,
        "needs_review": bool(needs_review),
        "tactic_classifier": source,
        "coarse_category": category,
    }


def _regex_category(title: str, content: str) -> tuple:
    """Fallback when BART is unavailable: decide the category from keywords."""
    k = _rank_tactics(title, content, _KIN)
    u = _rank_tactics(title, content, _UNR)
    if k and (not u or k[0][1] >= u[0][1]):
        return "VIOLENT", min(1.0, 0.5 + 0.1 * k[0][1]), False
    if u:
        return "UNREST", min(1.0, 0.5 + 0.1 * u[0][1]), False
    return "ROUTINE", 0.5, False


def _pipeline_to_coarse(labels: list, scores: list) -> dict:
    inv = {v: k for k, v in COARSE.items()}
    return {inv.get(lab, lab): float(sc) for lab, sc in zip(labels, scores)}


class TacticClassifier:
    def __init__(self, model: Any = None, force_regex: bool = False):
        self._model: Any = model
        self._tried = model is not None
        self._force_regex = force_regex
        self._candidate_labels = list(COARSE.values())

    def _ensure_model(self) -> Any:
        if self._force_regex:
            return None
        if self._tried:
            return self._model
        self._tried = True
        try:
            from transformers.pipelines import pipeline
            self._model = pipeline("zero-shot-classification", model=BART_MODEL)
            print("   🧠 Loaded BART coarse-category classifier.")
        except Exception as e:
            print(f"   ⚠️ BART unavailable ({e.__class__.__name__}); category decided by keywords.")
            self._model = None
        return self._model

    def classify(self, title: str, content: str = "") -> dict:
        title = title or ""
        negated = has_negation_cue(title)
        
        if is_blacklisted(title) and not has_any_tactic_signal(title):
            return _result("Other", "Other", 0.0, None, False, "blacklist", "ROUTINE")

        model = self._ensure_model()
        if model is None:
            category, conf, low = _regex_category(title, content)
            source = "regex"
        else:
            text = f"{title}. {str(content or '')[:600]}"
            out = model(text[:1000], candidate_labels=self._candidate_labels,
                        hypothesis_template=HYPOTHESIS_TEMPLATE, multi_label=True)
            coarse = _pipeline_to_coarse(out["labels"], out["scores"])
            category, conf, low = interpret_coarse(coarse)
            source = "bart"

        new_category = civic_override(category, title, content)
        if new_category != category:
            category = new_category
            low = False
            source = f"{source}+civic"
            
        acc_category = accident_override(category, title, content)
        if acc_category != category:
            category = acc_category
            low = False
            source = f"{source}+accident"

        t = assign_tactic(category, title, content)
        needs_review = bool(low or t["tactic_uncertain"] or negated)
        return _result(t["granular"], t["incident"], conf, t["secondary"],
                       needs_review, source, category)


_DEFAULT = None


def get_classifier() -> TacticClassifier:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = TacticClassifier()
    return _DEFAULT


def classify_tactic(title: str, content: str = "") -> dict:
    return get_classifier().classify(title, content)