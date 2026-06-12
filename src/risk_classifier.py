import json
import re
import spacy
from datetime import datetime

from src.config import DATA_DIR, HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD, MIN_RISK_SCORE, CIVIL_UNREST_SCORE, KEYWORDS
from src.utils import archive_to_historical

nlp = spacy.load("en_core_web_lg")

# ====================== CUSTOM ENTITY RULER (ZERO-SHOT NER) ======================
ruler = nlp.add_pipe("entity_ruler", before="ner", config={"overwrite_ents": True})

patterns = []
# 1. Map Geographic Locations
for loc in KEYWORDS["jk"]["locations"] + KEYWORDS["ne"]["locations"]:
    patterns.append({"label": "GPE", "pattern": [{"LOWER": loc.lower()}]})

# 2. Map Non-State Threat Actors (Insurgents / Militants)
for actor in KEYWORDS["jk"]["actors"] + KEYWORDS["ne"]["actors"]:
    patterns.append({"label": "THREAT_ACTOR", "pattern": [{"LOWER": actor.lower()}]})
    if "-" in actor:
        patterns.append({"label": "THREAT_ACTOR", "pattern": [{"LOWER": actor.lower().replace("-", " ")}]})

# 3. Map State Security Forces (Police, Army, Paramilitary)
for sf in KEYWORDS["jk"]["state_actors"] + KEYWORDS["ne"]["state_actors"]:
    patterns.append({"label": "SECURITY_FORCE", "pattern": [{"LOWER": sf.lower()}]})

ruler.add_patterns(patterns)

class RiskClassifier:
    def __init__(self):
        self.data_dir = DATA_DIR
        self.locations = {loc.lower() for loc in KEYWORDS["jk"]["locations"] + KEYWORDS["ne"]["locations"]}
        self.actors = {act.lower() for act in KEYWORDS["jk"]["actors"] + KEYWORDS["ne"]["actors"]}

        # ================== DYNAMIC CONTEXT ENGINE ==================
        conflict_terms = set(
            KEYWORDS.get("base_high_risk", []) +
            KEYWORDS.get("base_medium_risk", []) +
            KEYWORDS["jk"].get("high_risk", []) +
            KEYWORDS["ne"].get("high_risk", []) +
            list(self.actors)
        )
        conflict_terms.update([
            "security forces", "crpf", "army", "police", "insurgent",
            "rebel", "sf", "bsf", "forces", "troops", "personnel", "militant", "terrorist"
        ])
       
        escaped_terms = [re.escape(term.lower()) for term in conflict_terms]
        self.conflict_pattern = re.compile(rf"\b({'|'.join(escaped_terms)})\b", re.IGNORECASE)
        self.tactical_nouns = {term.lower() for term in conflict_terms if " " not in term}
        self.tactical_nouns.update(["villager", "driver", "worker", "civilian", "officer", "patrol", "convoy", "suspect"])

    # === Regex Casualty Extractor ===
    def _extract_casualties(self, text: str) -> dict:
        """
        Heuristic to extract casualties locally, split by severity.
        """
        if not text: 
            return {"killed": [], "injured": []}
            
        pattern = r'\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\b(?:\s+\w+){0,3}\s+(killed|injured|dead|martyred|slain|neutralised|neutralized|hurt|wounded)'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        killed, injured = [], []
        for count, action in matches:
            count, action = count.lower(), action.lower()
            if action in ["injured", "hurt", "wounded"]:
                injured.append(f"{count} {action}")
            else:
                killed.append(f"{count} {action}")
                
        return {"killed": list(set(killed)), "injured": list(set(injured))}

    def classify_article(self, article: dict) -> dict:
        text = f"{article.get('title', '')} {article.get('content', '')}"
        doc = nlp(text)
        text_lower = text.lower()

        # === Named Entity Matching ===
        matched_locs = [ent.text.title() for ent in doc.ents if ent.label_ == "GPE" and ent.text.lower() in self.locations]
        matched_actors = [ent.text.title() for ent in doc.ents if ent.label_ == "THREAT_ACTOR"]
        matched_state_actors = [ent.text.upper() for ent in doc.ents if ent.label_ == "SECURITY_FORCE"]

        # === RUTHLESS STRICT-LISTING HELPER ===
        def extract_core_entity(token):
            for ent in doc.ents:
                if token.i >= ent.start and token.i < ent.end:
                    if ent.label_ == "THREAT_ACTOR":
                        ent_text = ent.text.strip()
                        return ent_text.upper() if len(ent_text) <= 5 else ent_text.title()
            physical_targets = {
                "militant", "terrorist", "police", "army", "civilian", "rebel",
                "insurgent", "troop", "personnel", "soldier", "officer",
                "villager", "patrol", "convoy", "crpf", "bsf", "sf"
            }
            if token.pos_ in ["NOUN", "PROPN"]:
                lemma = token.lemma_.lower()
                if lemma in physical_targets:
                    return lemma.title()
            return None

        # === Role Extraction (Perpetrator / Victim / Claimed By) ===
        perpetrator = []
        victim = []
        claimed_by = []

        for token in doc:
            if token.lemma_ in ["kill", "attack", "ambush", "shoot", "neutralize", "gun", "bomb", "injure", "target"]:
                is_passive = any(child.dep_ == "auxpass" for child in token.children)
                for child in token.children:
                    if child.pos_ == "PRON": continue
                    extracted_entity = extract_core_entity(child)
                    if not extracted_entity: continue

                    if is_passive:
                        if child.dep_ == "nsubjpass":
                            victim.append(extracted_entity)
                        elif child.dep_ == "agent":
                            for sub in child.children:
                                if sub.dep_ == "pobj":
                                    sub_ent = extract_core_entity(sub)
                                    if sub_ent: perpetrator.append(sub_ent)
                    else:
                        if child.dep_ == "nsubj":
                            perpetrator.append(extracted_entity)
                        elif child.dep_ in ("dobj", "pobj"):
                            victim.append(extracted_entity)

            if "claim" in token.lemma_ or "responsib" in token.lemma_:
                for child in token.children:
                    if child.dep_ == "nsubj" and child.pos_ != "PRON":
                        extracted_entity = extract_core_entity(child)
                        if extracted_entity: claimed_by.append(extracted_entity)

        # === Regex Casualty Extractor ===
        regex_casualties = self._extract_casualties(text[:1500])

        # === Enhanced Casualty & Granular Incident Extraction ===
        granular_type = "Unknown"
        incident_mapping = {
            r"\b(ieds?|bombs?|grenades?|explosives?|blasts?)\b": "IED/Explosion",
            r"\b(encounters?|gunfights?|crossfires?|shootouts?)\b": "Gunfight/Encounter",
            r"\b(ambush(es)?)\b": "Ambush",
            r"\b(snip(e|ing)|assassinate|targeted attacks?)\b": "Targeted Attack",
            r"\b(caso|search operations?|cordons?|raids?)\b": "Search Operation",
            r"\b(infiltrations?|cross-border)\b": "Border Infiltration",
            r"\b(stone pelting)\b": "Stone Pelting",
            r"\b(protests?|riots?|curfews?|clash(es)?|economic blockades?|bandhs?|hartals?)\b": "Civil Unrest",
            r"\b(arson|vandalism|torched)\b": "Arson/Vandalism"
        }

        title_lower = article.get("title", "").lower()
        confidence_scores = {inc_type: 0.0 for inc_type in incident_mapping.values()}
       
        for pattern, inc_type in incident_mapping.items():
            title_matches = len(re.findall(pattern, title_lower))
            if title_matches > 0:
                confidence_scores[inc_type] += (title_matches * 2.0)
       
        for pattern, inc_type in incident_mapping.items():
            body_matches = len(re.findall(pattern, text_lower))
            if body_matches > 0:
                confidence_scores[inc_type] += (body_matches * 1.0)
       
        best_match = max(confidence_scores, key=lambda k: confidence_scores[k])
        if confidence_scores[best_match] > 0:
            granular_type = best_match

        if granular_type in ["IED/Explosion", "Gunfight/Encounter", "Ambush", "Targeted Attack", "Search Operation", "Border Infiltration"]:
            incident_type = "Kinetic"
        elif granular_type in ["Stone Pelting", "Civil Unrest", "Arson/Vandalism"]:
            incident_type = "Unrest"
        else:
            incident_type = "Other"

        is_in_region = any(loc.lower() in self.locations for loc in matched_locs)
        has_conflict_context = bool(self.conflict_pattern.search(text_lower)) or bool(matched_actors)
        has_casualties = bool(regex_casualties)

        # === UPGRADE: Action-Aware Infrastructure Circuit Breaker ===
        softer_context_blacklist = [
            "cricket", "tournament", "matches", "championship", "sports", "yoga",
            "festival", "white-collar", "jkssb", "verification", "exam", "paper leak",
            "results", "seminar", "conferred", "award", "golf", "hockey",
            "pachayat", "elections", "voters", "tourism boom", "pageant", "cultural festival"
        ]
        
        # 1. Track development nouns
        development_context = ["four-laning", "inaugurates", "construction", "tender", "allocated", "funding", "budget", "railway link", "tunnel", "highway", "bridge"]
        
        # 2. Track tactical action verbs
        tactical_action_signals = ["block", "shut", "ambush", "attack", "clash", "fired", "blast", "encounter", "protest", "stone pelting", "gunfight", "killing"]

        is_false_positive = any(word in title_lower for word in softer_context_blacklist)
        is_infra_development = any(word in title_lower for word in development_context)
        has_tactical_action = any(word in title_lower for word in tactical_action_signals)

        if (incident_type in ["Kinetic", "Unrest"]) and is_in_region and not is_false_positive:
            if is_infra_development and not has_tactical_action and not (matched_actors or perpetrator or claimed_by or len(regex_casualties["killed"]) > 0):
                granular_type = "Infrastructure Development"
                incident_type = "Other"
                final_score = 1.5
            elif has_conflict_context or has_casualties:
                final_score = MIN_RISK_SCORE if incident_type == "Kinetic" else CIVIL_UNREST_SCORE
                if matched_actors or perpetrator or claimed_by:
                    final_score += 2.0
                final_score = min(10.0, final_score)
            else:
                final_score = 4.0
        else:
            final_score = min(3.0, 0.0 + (len(matched_locs) * 0.5))

        if granular_type == "Infrastructure Development":
            incident_type = "Other"

        risk_level = "HIGH" if final_score >= HIGH_RISK_THRESHOLD else "MEDIUM" if final_score >= MEDIUM_RISK_THRESHOLD else "LOW"

        article.update({
            "ner_locations": list(set(matched_locs)),
            "ner_actors": list(set(matched_actors)),
            "ner_state_actors": list(set(matched_state_actors)),
            "perpetrator": list(set(perpetrator)),
            "victim_target": list(set(victim)),
            "claimed_by": list(set(claimed_by)),
            "granular_incident_type": granular_type,
            "casualties_killed": regex_casualties,
            "casualties_injured": [], 
            "final_risk_score": final_score,
            "final_risk_level": risk_level,
            "incident_type": incident_type,
            "classified_at": datetime.now().isoformat()
        })
        return article

    def process_all_raw_files(self):
        import pandas as pd
        print("🧠 Running Precision Risk Classifier (Data-Driven + Safety Valve)...")
        processed_count = 0
        archived_count = 0
        
        for json_file in self.data_dir.glob("*.json"):
            if "twitter" in json_file.name.lower():
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    articles = json.load(f)

                needs_save = False
                for article in articles:
                    self.classify_article(article)
                    processed_count += 1
                    needs_save = True
                    
                    # ===Push to Dashboard Archives ===
                    if article.get("final_risk_score", 0) >= MIN_RISK_SCORE:
                        archive_to_historical(article)
                        archived_count += 1

                if needs_save:
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(articles, f, indent=2, ensure_ascii=False)
                        
                    # ===Sync to local CSV for Dashboard ===
                    csv_path = json_file.with_suffix('.csv')
                    pd.DataFrame(articles).to_csv(csv_path, index=False)

            except Exception as e:
                print(f"⚠️ Error processing {json_file.name}: {e}")

        print(f"🎉 Enhanced classification complete. Processed: {processed_count} | Archived: {archived_count}")
        return processed_count

if __name__ == "__main__":
    classifier = RiskClassifier()
    classifier.process_all_raw_files()