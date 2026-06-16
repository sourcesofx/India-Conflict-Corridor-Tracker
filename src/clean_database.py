import json
import re
import pandas as pd

from src.config import DATA_DIR, KEYWORDS, MIN_RISK_SCORE, CIVIL_UNREST_SCORE, JSON_RETENTION_DAYS
from src.utils import is_article_too_old
from src.historical_purge import purge_historical

# ================== CONFIG ==================
LOG_PURGED = True

def strict_retrospective_scrub():
    """
    Performs retrospective scrubbing of the data lake (Daily Optimization).
    Removes low-quality, out-of-region, duplicate, and old articles.
    Maintains parity by synchronizing JSON arrays with companion CSVs.
    """
    print("🧼 Initializing Strict Spatial, Quality, and Lexical Scrubbing Protocol...")

    jk_locs = {loc.lower() for loc in KEYWORDS["jk"]["locations"]}
    ne_locs = {loc.lower() for loc in KEYWORDS["ne"]["locations"]}
    valid_territories = jk_locs.union(ne_locs)

    total_purged = 0
    total_retained = 0
    purge_reasons = {"low_score": 0, "out_of_region": 0, "duplicate": 0, "too_old": 0, "manual": 0}

    # ==========================================
    # Global Lexical Memory
    # ==========================================
    global_seen_events = [] 
    manual_purge_urls = set()

    for json_file in DATA_DIR.glob("*.json"):
        if "twitter" in json_file.name.lower():
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                articles = json.load(f)

            pruned_articles = []
            articles = sorted(articles, key=lambda x: x.get("final_risk_score", 0), reverse=True)

            for article in articles:
                score = article.get("final_risk_score", 0)
                ner_locations = [l.lower() for l in article.get("ner_locations", [])]
                title = article.get("title", "").lower()
                content = article.get("content", "").lower()
                tactic = article.get("granular_incident_type", "Unknown")
                published_date = article.get("published_date")
                is_manual_purge = bool(article.get("manual_purge"))

                is_in_region_ner = any(loc in valid_territories for loc in ner_locations)
                has_regional_keyword = any(loc in title or loc in content for loc in valid_territories)
                is_in_region = is_in_region_ner or has_regional_keyword
                
                # Datalake retention guardrail
                is_too_old = is_article_too_old(published_date, JSON_RETENTION_DAYS)

                is_dup = False
                words = set(re.findall(r'\b\w{4,}\b', title))

                if is_in_region and not is_too_old:
                    for seen_words in global_seen_events:
                        if words and seen_words:
                            overlap = len(words.intersection(seen_words))
                            if overlap / min(len(words), len(seen_words)) > 0.65:
                                is_dup = True
                                break

                required_score = CIVIL_UNREST_SCORE if tactic == "Civil Unrest" else MIN_RISK_SCORE

                if score >= required_score and is_in_region and not is_dup and not is_too_old and not is_manual_purge:
                    pruned_articles.append(article)
                    global_seen_events.append(words)
                else:
                    total_purged += 1
                    if is_manual_purge:
                        purge_reasons["manual"] += 1
                        manual_purge_urls.add(article.get("url"))
                    elif is_too_old:
                        purge_reasons["too_old"] += 1
                    elif is_dup:
                        purge_reasons["duplicate"] += 1
                    elif score < required_score:
                        purge_reasons["low_score"] += 1
                    elif not is_in_region:
                        purge_reasons["out_of_region"] += 1

                    if LOG_PURGED:
                        reason = "MANUAL" if is_manual_purge else ("OLD" if is_too_old else ("DUP" if is_dup else ("SCORE" if score < required_score else "LOC")))
                        print(f"   🗑️ Purged [{reason}] | Score={score:.1f} | {article.get('title', '')[:80]}...")

            total_retained += len(pruned_articles)

            # 1. Update the primary local JSON file
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(pruned_articles, f, indent=2, ensure_ascii=False)

            # 2. Sync clean states to companion local CSVs for data lake parity
            csv_path = json_file.with_suffix('.csv')
            if pruned_articles:
                pd.DataFrame(pruned_articles).to_csv(csv_path, index=False)
            elif csv_path.exists():
                csv_path.unlink() 

        except Exception as e:
            print(f"⚠️ Failed to scrub {json_file.name}: {e}")

    # ================== HISTORICAL ARCHIVE PURGE ==================
    hist_summary = None
    if manual_purge_urls:
        try:
            hist_summary = purge_historical(
                manual_purge_urls, hist_root=DATA_DIR.parent / "historical", write=True
            )
        except Exception as e:
            print(f"⚠️ Historical purge failed: {e}")

    # ================== FINAL REPORT ==================
    print("\n" + "="*65)
    print("🏁 SCRUBBING METRICS REPORT")
    print("="*65)
    print(f"🗑️  Total Purged:              {total_purged}")
    print(f"   ├── Manually Flagged:        {purge_reasons['manual']}")
    print(f"   ├── Too Old (> {JSON_RETENTION_DAYS} days): {purge_reasons['too_old']}")
    print(f"   ├── Lexical Duplicates:      {purge_reasons['duplicate']}")
    print(f"   ├── Low Score:               {purge_reasons['low_score']}")
    print(f"   └── Out of Region:           {purge_reasons['out_of_region']}")
    print(f"🛡️  Total Retained:            {total_retained}")
    if hist_summary is not None:
        print(f"🗂️  Historical rows purged:    {hist_summary.get('rows_removed', 0)}"
              f"  (backup: {hist_summary.get('backup_path')})")
    print("="*65 + "\n")

if __name__ == "__main__":
    strict_retrospective_scrub()