import json
import re
import spacy
from datetime import datetime

from src.config import DATA_DIR, HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD, MIN_RISK_SCORE, CIVIL_UNREST_SCORE, KEYWORDS
from src.utils import archive_to_historical
from src.tactic_classifier import classify_tactic
from src.extraction import extract_casualties, summarize_casualties
from src.spacy_ext import extract_roles

nlp = spacy.load("en_core_web_lg")

# ====================== CUSTOM ENTITY RULER (ZERO-SHOT NER) ======================
ruler = nlp.add_pipe(
    "entity_ruler",
    before="ner",
    config={"overwrite_ents": True, "phrase_matcher_attr": "LOWER"},
)

patterns = []
# 1. Map Geographic Locations
for loc in KEYWORDS["jk"]["locations"] + KEYWORDS["ne"]["locations"]:
    patterns.append({"label": "GPE", "pattern": loc})

# 2. Map Non-State Threat Actors (Insurgents / Militants)
for actor in KEYWORDS["jk"]["actors"] + KEYWORDS["ne"]["actors"]:
    patterns.append({"label": "THREAT_ACTOR", "pattern": actor})
    if "-" in actor:
        patterns.append({"label": "THREAT_ACTOR", "pattern": actor.replace("-", " ")})

# 3. Map State Security Forces (Police, Army, Paramilitary)
for sf in KEYWORDS["jk"]["state_actors"] + KEYWORDS["ne"]["state_actors"]:
    patterns.append({"label": "SECURITY_FORCE", "pattern": sf})

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

    def classify_article(self, article: dict) -> dict:
        text = f"{article.get('title', '')} {article.get('content', '')}"
        doc = nlp(text)
        text_lower = text.lower()

        # === Named Entity Matching ===
        matched_locs = [ent.text.title() for ent in doc.ents if ent.label_ == "GPE" and ent.text.lower() in self.locations]
        matched_actors = [ent.text.title() for ent in doc.ents if ent.label_ == "THREAT_ACTOR"]
        matched_state_actors = [ent.text.upper() for ent in doc.ents if ent.label_ == "SECURITY_FORCE"]

        # === Role Extraction (Perpetrator / Victim / Claimed By) ===
        roles = extract_roles(doc)
        perpetrator = roles["perpetrator"]
        victim = roles["victim"]
        claimed_by = roles["claimed_by"]

        # === Casualty Extraction (counts + affiliation) ===
        casualties = extract_casualties(text[:1500])
        cas_summary = summarize_casualties(casualties)

        # === Tactic classification (hybrid: BART coarse gate + keyword tactic) ===
        tactic = classify_tactic(article.get("title", ""), article.get("content", ""))
        granular_type = tactic["granular_incident_type"]
        incident_type = tactic["incident_type"]
        title_lower = article.get("title", "").lower()

        is_in_region = any(loc.lower() in self.locations for loc in matched_locs)
        has_conflict_context = bool(self.conflict_pattern.search(text_lower)) or bool(matched_actors)
        has_casualties = cas_summary["has_casualties"]

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
            if is_infra_development and not has_tactical_action and not (matched_actors or perpetrator or claimed_by or cas_summary["total_killed"] > 0):
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
            "casualties_killed": casualties["killed"],
            "casualties_injured": casualties["injured"],
            "total_killed": cas_summary["total_killed"],
            "total_injured": cas_summary["total_injured"], 
            "final_risk_score": final_score,
            "final_risk_level": risk_level,
            "incident_type": incident_type,
            "tactic_confidence": tactic.get("tactic_confidence"),
            "secondary_tactic": tactic.get("secondary_tactic"),
            "needs_review": tactic.get("needs_review", False),
            "coarse_category": tactic.get("coarse_category"),
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