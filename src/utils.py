import re
import json
import pandas as pd
from src.config import KEYWORDS, DATA_DIR


def extract_content_with_trafilatura(url: str) -> str:
    """
    Extracts clean, readable article text using Trafilatura.
    Used to enrich content for better SpaCy classification.
    """
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                include_formatting=False
            )
            if text and len(text) > 200:
                return text[:8000]
    except Exception as e:
        if "lxml_html_clean" in str(e):
            print("   ⚠️ Trafilatura missing dependency. Run: pip install \"lxml[html-clean]\"")
        else:
            print(f"   ⚠️ Trafilatura failed for {url}: {e}")
    return ""


def get_all_existing_articles() -> dict:
    """Returns {url: published_date} for global deduplication."""
    existing = {}
    for json_file in DATA_DIR.glob("*.json"):
        if "twitter" in json_file.name.lower():
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                for article in json.load(f):
                    url = article.get("url")
                    if url:
                        existing[url] = article.get("published_date", "")
        except Exception:
            continue
    return existing


def normalize_text(text: str) -> str:
    return text.lower().replace("-", " ")


def contains_keywords(text: str) -> list:
    text_norm = normalize_text(text)
    matched = []
    all_kws = []

    for region in ["jk", "ne"]:
        if region in KEYWORDS:
            all_kws.extend(KEYWORDS[region].get("high_risk", []))
            all_kws.extend(KEYWORDS[region].get("medium_risk", []))
            all_kws.extend(KEYWORDS[region].get("actors", []))
            all_kws.extend(KEYWORDS[region].get("locations", []))

    all_kws.extend(KEYWORDS.get("base_high_risk", []))
    all_kws.extend(KEYWORDS.get("base_medium_risk", []))
    all_kws = sorted(list(set(all_kws)), key=len, reverse=True)

    for kw in all_kws:
        if len(kw) >= 4 and kw in text_norm:
            matched.append(kw)
    return matched


def lexical_deduplicate(df: pd.DataFrame, max_results: int | None = None) -> pd.DataFrame:
    if df.empty:
        return df

    deduped_indices = []
    seen_words_list = []

    for idx, row in df.iterrows():
        words = set(re.findall(r'\b\w{4,}\b', str(row.get('title', '')).lower()))
        is_dup = False

        for seen_words in seen_words_list:
            if words and seen_words:
                overlap = len(words.intersection(seen_words))
                if overlap / min(len(words), len(seen_words)) > 0.65:
                    is_dup = True
                    break

        if not is_dup:
            seen_words_list.append(words)
            deduped_indices.append(idx)

        if max_results and len(deduped_indices) >= max_results:
            break

    return df.loc[deduped_indices].copy()


def is_article_too_old(published_date, max_days: int = 7) -> bool:
    """
    Returns True if the article is mathematically older than max_days.
    Defaults to False (keep the article) if the date is completely unreadable,
    preventing strict HTML errors from dropping breaking intelligence.
    """
    if not published_date:
        return False

    try:
        import pandas as pd
        from datetime import datetime
        if isinstance(published_date, str):
            pub_dt = pd.to_datetime(published_date, errors="coerce")
        else:
            pub_dt = pd.to_datetime(published_date)

        if pd.isna(pub_dt):
            return False
        
        if pub_dt.tzinfo is not None:
            pub_dt = pub_dt.tz_localize(None)

        age_days = (datetime.now() - pub_dt).days
        return age_days > max_days

    except Exception:
        return False


def archive_to_historical(article: dict):
    """
    Archives articles to monthly partitioned CSVs.
    Maps purely local SpaCy NER fields to Dashboard-compatible columns.
    """
    try:
        import pandas as pd
        from datetime import datetime
        from pathlib import Path

        pub_date_str = article.get("published_date") or article.get("timestamp")
        if not pub_date_str:
            return

        try:
            dt = pd.to_datetime(pub_date_str)
        except Exception:
            dt = datetime.now()

        year = dt.strftime("%Y")
        month = dt.strftime("%m")

        archive_dir = Path("data/historical") / year
        archive_dir.mkdir(parents=True, exist_ok=True)
        csv_path = archive_dir / f"{month}.csv"

        def format_list(val):
            if not val: return ""
            return ", ".join(val) if isinstance(val, list) else str(val)

        def format_casualties(val):
            """Smart formatter for casualties_killed dict (from classifier regex) or legacy list."""
            if not val:
                return ""
            if isinstance(val, dict):
                killed = ", ".join(val.get("killed", [])) if val.get("killed") else ""
                injured = ", ".join(val.get("injured", [])) if val.get("injured") else ""
                parts = []
                if killed: parts.append(f"Killed: {killed}")
                if injured: parts.append(f"Injured: {injured}")
                return " | ".join(parts) if parts else ""
            if isinstance(val, list):
                return ", ".join(val)
            return str(val)

        # SPACY-SPECIFIC MAPPING
        actors = article.get("ner_actors", [])
        state_actors = article.get("ner_state_actors", [])
        all_perps = list(set(actors + state_actors))
        
        row = {
            "timestamp": article.get("timestamp"),
            "published_date": article.get("published_date"),
            "source": article.get("source_name") or article.get("source", "Unknown"),
            "title": article.get("title"),
            "url": article.get("url"),
            "final_risk_score": article.get("final_risk_score", 0),
            "incident_type": article.get("incident_type", "Unknown"),
            "granular_incident_type": article.get("granular_incident_type", "Operational Activity"),
            
            # Dashboard Schema Mapping (Using purely local SpaCy extractions)
            "Render_Perp": format_list(all_perps),
            "Render_Target": format_list(article.get("ner_locations", [])),
            "Render_Casualties": format_casualties(article.get("casualties_killed")),
            
            "region": article.get("region"),
            "source_type": article.get("source_type"),
        }

        df = pd.DataFrame([row])

        if csv_path.exists():
            df.to_csv(csv_path, mode="a", header=False, index=False)
        else:
            df.to_csv(csv_path, mode="w", header=True, index=False)
            
    except Exception as e:
        print(f"⚠️ Failed to archive to historical: {e}")