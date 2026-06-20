from __future__ import annotations

ATTACK_LEMMAS = {
    "kill", "shoot", "attack", "ambush", "bomb", "gun", "fire", "assault",
    "abduct", "kidnap", "behead", "lynch", "stab", "hurl", "lob", "detonate",
    "target", "injure", "wound", "martyr", "eliminate", "neutralize",
    "neutralise", "strike", "raid", "storm", "open",
}
CLAIM_LEMMAS = {"claim", "own", "admit"}
NEG_GOVERNORS = {"fail", "foil", "avert", "thwart", "prevent", "deny",
                 "abort", "bid", "attempt", "plan", "plot"}
_DET = {"a", "an", "the"}

_ROLE_STOP = {
    # pronouns / relativisers
    "he", "she", "it", "they", "them", "him", "her", "his", "their", "its",
    "this", "that", "these", "those", "who", "which", "we", "i", "you", "us",
    # bare quantifiers / number words
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "several", "many", "some", "few", "both", "others", "another",
    "dozens", "scores", "hundreds", "thousands",
    # generic collectives
    "people", "member", "members", "group", "men", "man", "woman", "women",
    "person", "persons",
    # time words
    "morning", "evening", "afternoon", "night", "midnight", "noon", "dawn",
    "dusk", "today", "yesterday", "tomorrow",
    # adjectives observed standing alone as a bogus role
    "fresh", "national",
}
_NUMERIC_LEAD = _DET | {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
}


def _is_noise(text: str) -> bool:
    """True if a role span carries no identifiable actor."""
    toks = (text or "").lower().split()
    while toks and (toks[0] in _NUMERIC_LEAD or toks[0].isdigit()):
        toks = toks[1:]
    if not toks:
        return True
    return all(t in _ROLE_STOP or t.isdigit() for t in toks)


def _expand_conj(token):
    """A token plus anything truly conjoined to it ('militants and gunmen')."""
    out = [token]
    for child in token.children:
        if child.dep_ == "conj" and not getattr(child, "is_punct", False):
            out.extend(_expand_conj(child))
    return out


def _is_negated(verb):
    for child in verb.children:
        if child.dep_ == "neg":
            return True
    head, hops = verb.head, 0
    while head is not None and head is not verb and hops < 3:
        if head.lemma_.lower() in NEG_GOVERNORS:
            return True
        if head is head.head:
            break
        head, hops = head.head, hops + 1
    return False


def _span_text(token, doc):
    """Resolve a token to the entity span or noun phrase containing it."""
    if getattr(token, "ent_type_", ""):
        for ent in getattr(doc, "ents", []) or []:
            if ent.start <= token.i < ent.end:
                return ent.text
    try:
        chunks = doc.noun_chunks
    except (AttributeError, ValueError, TypeError):
        chunks = None
    if chunks is not None:
        for chunk in chunks:
            if chunk.start <= token.i < chunk.end:
                words = [w.text for w in chunk if not getattr(w, "is_punct", False)]
                while words and words[0].lower() in _DET:
                    words = words[1:]
                return " ".join(words) if words else token.text
    return token.text


def _emit(tokens, doc):
    out = []
    for t in tokens:
        if getattr(t, "is_punct", False) or getattr(t, "is_space", False):
            continue
        out.append(_span_text(t, doc))
    return out


def _collect(items):
    seen, out = set(), []
    for it in items:
        if _is_noise(it):
            continue
        k = it.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


def extract_roles(doc) -> dict:
    perpetrator, victim, claimed_by = [], [], []

    for token in doc:
        lemma = token.lemma_.lower()

        if token.pos_ == "VERB" and lemma in ATTACK_LEMMAS:
            if _is_negated(token):
                continue
            subjs, objs, agents, pass_subjs = [], [], [], []
            for child in token.children:
                if child.dep_ == "nsubj":
                    subjs.extend(_expand_conj(child))
                elif child.dep_ in ("nsubjpass", "nsubj:pass"):
                    pass_subjs.extend(_expand_conj(child))
                elif child.dep_ in ("dobj", "obj"):
                    objs.extend(_expand_conj(child))
                elif child.dep_ == "agent":
                    for g in child.children:
                        if g.dep_ in ("pobj", "obj"):
                            agents.extend(_expand_conj(g))
            if pass_subjs:
                victim.extend(_emit(pass_subjs, doc))
                perpetrator.extend(_emit(agents, doc))
            else:
                perpetrator.extend(_emit(subjs, doc))
                victim.extend(_emit(objs, doc))

        elif token.pos_ == "VERB" and lemma in CLAIM_LEMMAS:
            kids = list(token.children)
            if any(c.lemma_.lower() in {"responsibility", "attack", "blast",
                                        "bombing", "killing"} for c in kids):
                for child in kids:
                    if child.dep_ == "nsubj":
                        claimed_by.extend(_emit(_expand_conj(child), doc))

    return {
        "perpetrator": _collect(perpetrator),
        "victim": _collect(victim),
        "claimed_by": _collect(claimed_by),
    }