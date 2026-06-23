import re

_ADMIT = [
    r"kill\w*", r"shot dead", r"shoots? dead", r"gun(?:s|ned)? down",
    r"gunfights?", r"open(?:s|ed)? fire", r"firing on",
    r"blast\w*", r"grenade\w*", r"\bied\b",
    r"ambush\w*", r"armed attack\w*",
    r"injured in (?:a |an )?(?:knife|grenade|firing|gun|bomb|blast)\w*",
]

_VETO = [
    # law-enforcement action / search-op
    r"arrest\w*", r"held", r"appreh\w*", r"detain\w*", r"nabbed", r"custody",
    r"bust\w*", r"seiz\w*", r"recover\w*", r"demolish\w*", r"crackdown", r"raid\w*",
    # civil unrest (has its own log)
    r"protest\w*", r"rally", r"bandh", r"sit-?in",
    # statements / commemorations / pressers
    r"prayer\w*", r"tribute", r"greeting\w*", r"homage", r"commemorat\w*",
    r"memorial", r"appeal\w*", r"urges?", r"review\w*", r"charts path",
    r"demand\w*", r"condemn\w*",
    # wildlife
    r"bear attack\w*", r"mauled", r"leopard", r"elephant", r"langur",
    r"tiger", r"wildlife", r"poach\w*", r"traffick\w*",
    # accidents / disasters
    r"factory fire", r"caught fire", r"fire breaks", r"gorge", r"drown\w*",
    r"electrocut\w*", r"electric shock", r"lightning", r"landslide",
    # vehicle / rail accidents (struck-by, not an attack)
    r"hit by (?:\w+\s+){0,3}?(?:vehicle|truck|bus|car|train|tipper|tractor|lorry|jeep|lorry|tempo|auto)",
    r"run over by", r"mowed down by (?:a )?(?:vehicle|truck|bus|car|train)",
    r"road accident", r"road mishap",
    # non-incident movement
    r"released", r"shifted", r"relocat\w*",
]

_ADMIT_RE = re.compile(r"\b(?:" + "|".join(_ADMIT) + r")\b", re.I)
_VETO_RE = re.compile(r"\b(?:" + "|".join(_VETO) + r")\b", re.I)

# ordnance FIND (weapon recovered, no detonation) — never a kinetic event
_ORDNANCE_FIND_RE = re.compile(
    r"\b(?:shell|mortar|grenade|ied|ordnance|explosive|ammunition)s?\b"
    r"[^.]*\b(?:found|recover\w*|defus\w*|seiz\w*)\b",
    re.I,
)

def is_kinetic_log_eligible(row):
    """True only if the title reads as a genuine kinetic attack and trips no veto.
    Accepts a dict or a pandas row (both expose .get)."""
    title = str(row.get("title", "") or "")
    if _VETO_RE.search(title):
        return False
    if _ORDNANCE_FIND_RE.search(title):
        return False
    return bool(_ADMIT_RE.search(title))