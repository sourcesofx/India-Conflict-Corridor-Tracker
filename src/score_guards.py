from __future__ import annotations
import re

# --- Lever 1: aftermath / derivative framing ------------------------------- #
_AFTERMATH_CUES = (
    "demands action", "demand action", "demands justice", "demand justice",
    "demands probe", "demand probe", "seeks probe", "seek probe",
    "seeks justice", "seek justice", "calls for probe", "call for probe",
    "condemns", "condemned", "condemn", "decries", "slams", "flays",
    "role limited", "role is limited",
    "issues statement", "press meet", "presser", "memorandum submitted",
    "over admission", "admission of",
    "pays tribute", "mourns", "last rites", "funeral",
    "urges calm", "urge calm", "appeals for calm", "appeal for calm", "forensic probe", "probe into", "investigation into",
    "starts probe", "orders probe", "ordered probe", "launches probe",
    "exhumed", "exhumation", "after fortnight", "fortnight", "months after", "weeks after",
    "days after", "year after", "anniversary", "summons", "summoned", "chargesheet", "charge sheet",
    "verdict", "convicted", "acquitted", "sentenced", "handed over", "given to kin", "handed to kin",
    "encounter case", "case registered", "returns home",
)

# Fresh-action / caused-casualty cues. Any of these means a LIVE incident,
# so the dampener is vetoed (keep the score).
_FRESH_ACTION_RX = re.compile(
    r"\b("
    r"(?:leaves|leaving|left)\s+\S+\s+(?:killed|injured|dead|wounded|hurt)|"
    r"kills|injures|injuring|wounds|wounding|"
    r"opens? fire|opened fire|turns violent|"
    r"tear gas|lobbed|hurled|torched|set ablaze|detonated|"
    r"gunned down|shot dead|ambushed|attacked|attack on|stormed|stabbed"
    r")\b",
    re.IGNORECASE,
)


def _hit(text: str, terms) -> bool:
    return any(term in text for term in terms)


def is_derivative_aftermath(title: str) -> bool:
    head = (title or "").lower()
    if not _hit(head, _AFTERMATH_CUES):
        return False
    if _FRESH_ACTION_RX.search(head):
        return False
    return True


# --- Lever 2: concrete-evidence gate for the high-risk floor ---------------- #
_KINETIC_HEADLINE_CUES = (
    "gunfight", "encounter", "firefight", "shootout", "crossfire", "firing",
    "blast", "explosion", "ied", "grenade", "bomb", "mortar", "landmine",
    "ambush", "infiltration", "fidayeen", "opened fire", "open fire",
    "shot dead", "gunned down", "killed", "injured", "abducted", "kidnapped",
    "lynched", "attack", "bodies found", "body found", "bodies recovered", "found dead",
    "dead body", "dead bodies", "hostage", "hostages", "abduction",
    "beheaded", "mutilated", "massacre"
)
_UNREST_HEADLINE_CUES = (
    "stone pelting", "stone-pelting", "stone throwing", "arson", "torched",
    "set ablaze", "clash", "riot", "curfew", "tear gas", "turns violent",
    "lathicharge", "lathi charge", "blockade", "bandh", "hartal",
    "poll violence", "election violence", "electoral violence",
    "ethnic violence", "communal violence", "mob violence", "political violence",
)

def _secop_evidence(head: str) -> bool:
    """Counter-insurgency operation evidence in the headline: a recovery /
    seizure / camp bust, OR an actor-specific arrest (militant/insurgent/cadre/
    terrorist + arrest/held/nabbed). Deliberately precise -- bare 'arrested' or
    'raid' is excluded so it does NOT re-floor administrative aftermath
    ('NIA attaches... arrested accused') or protests ('leaders are arrested')."""
    hard = (
        "ammunition", "cache", "bunker", "hideout",
        "recover arms", "arms recover", "arms recovered", "arms recovery",
        "seize arms", "seized arms", "arms seized", "arms and ammunition",
        "weapons recovered", "explosives recovered", "grenades recovered",
        "ied recovered", "militant camp", "insurgent camp",
    )
    if any(h in head for h in hard):
        return True
    actor = ("militant" in head or "insurgent" in head
             or "cadre" in head or "terrorist" in head)
    action = ("arrest" in head or "held" in head or "nabbed" in head
              or "detained" in head or "apprehend" in head)
    return actor and action

def floor_is_justified(title, incident_type, matched_actors, perpetrator,
                       claimed_by, total_killed=0, total_injured=0,
                       content="") -> bool:
    head = (title or "").lower()
    if is_derivative_aftermath(title):
        return False
    casualty = (total_killed or 0) > 0 or (total_injured or 0) > 0
    if incident_type == "Kinetic":
        cue = _hit(head, _KINETIC_HEADLINE_CUES) or _secop_evidence(head)
    elif incident_type == "Unrest":
        unrest_scope = head + " " + (str(content or "")[:_DATELINE_CHARS].lower())
        cue = _hit(unrest_scope, _UNREST_HEADLINE_CUES)
    else:
        cue = False
    if (matched_actors or perpetrator or claimed_by) and (cue or casualty):
        return True
    if casualty:
        return True
    return cue

_DATELINE_CHARS = 250


def region_anchored(title, content, matched_locs, coverage_states=()) -> bool:
    head = (str(title or "").lower()
            + " " + str(content or "")[:_DATELINE_CHARS].lower())
    if any(str(loc).lower() in head for loc in (matched_locs or [])):
        return True
    if any(str(s).lower() in head for s in (coverage_states or ())):
        return True
    return False