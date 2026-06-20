import re
import json
import pandas as pd
import numpy as np
from src.config import KEYWORDS, DATA_DIR
from src.extraction import format_casualties


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

DEDUP_STOPLIST = {
    "kashmir", "jammu", "india", "indian", "northeast", "assam", "manipur",
    "police", "force", "forces", "security", "army", "militant", "militants",
    "terrorist", "terrorists", "encounter", "attack", "attacks", "killed",
    "dead", "death", "injured", "protest", "protests", "operation", "district",
    "after", "amid", "over", "said", "says", "near", "from", "into", "with",
    "their", "report", "reports", "official", "officials", "year", "years",
}

_EMBEDDER = None
_EMBEDDER_TRIED = False


def _get_default_embedder():
    global _EMBEDDER, _EMBEDDER_TRIED
    if _EMBEDDER_TRIED:
        return _EMBEDDER
    _EMBEDDER_TRIED = True
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        def _encode(texts):
            return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

        _EMBEDDER = _encode
        print("   🧠 Loaded MiniLM sentence-embedding model for semantic dedup.")
    except Exception as e:
        print(f"   ⚠️ sentence-transformers not available ({e.__class__.__name__}); "
              f"dedup using word-overlap only. Run: pip install sentence-transformers")
        _EMBEDDER = None
    return _EMBEDDER

def fix_mojibake(text: str) -> str:
    """Repair UTF-8 text mis-decoded as Windows-1252 (mojibake)."""
    if not text or not any(m in text for m in ("â€", "Ã", "Â")):
        return text
    try:
        return text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _title_tokens(title) -> set:
    words = re.findall(r"\b[a-z][a-z'-]{3,}\b", str(title).lower())
    return set(w for w in words if w not in DEDUP_STOPLIST)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _date_bucket(row, window_days: int):
    for col in ("timestamp", "published_date"):
        val = row.get(col)
        if val:
            dt = pd.to_datetime(val, errors="coerce")
            if not pd.isna(dt):
                if getattr(dt, "tzinfo", None) is not None:
                    dt = dt.tz_localize(None)
                return int(dt.toordinal() // window_days)
    return "NA"


_DISTRICT_KEYS = None
def _district_keys() -> set:
    """Lazily-cached lowercased set of known district names (from config)."""
    global _DISTRICT_KEYS
    if _DISTRICT_KEYS is None:
        try:
            from src.config import DISTRICT_COORDS
            _DISTRICT_KEYS = {str(k).lower() for k in DISTRICT_COORDS}
        except Exception:
            _DISTRICT_KEYS = set()
    return _DISTRICT_KEYS

def _event_locations(row) -> set:
    """Places anchoring this event: NER locations if present, else any known
    district named in the title (fallback for rows without NER, incl. tests)."""
    raw = row.get("ner_locations")
    if isinstance(raw, str):
        import ast
        try: raw = ast.literal_eval(raw)
        except Exception: raw = []
    if isinstance(raw, list) and raw:
        return {str(x).lower() for x in raw}
    head = str(row.get("title", "")).lower()
    return {d for d in _district_keys() if d in head}


def lexical_deduplicate(df: pd.DataFrame, max_results: int | None = None,
                        threshold: float = 0.5, window_days: int = 3,
                        use_embeddings: bool = True, embedding_threshold: float = 0.78,
                        embedder=None) -> pd.DataFrame:
    """
    Collapse duplicate reports of the same event. Within each region+time block,
    two articles are duplicates if EITHER titles share enough words (Jaccard >=
    threshold) OR meanings are close (cosine >= embedding_threshold) -- UNLESS the
    two name different, non-overlapping places, in which case they are distinct
    events (e.g. "...killed in Pulwama" vs "...killed in Kupwara") and never merge.
    """
    if df is None or df.empty:
        return df

    work = df.copy()
    if "final_risk_score" in work.columns:
        work = work.sort_values("final_risk_score", ascending=False, kind="stable")

    embeddings = None
    if use_embeddings:
        if embedder is None:
            embedder = _get_default_embedder()
        if embedder is not None:
            texts = [f"{r.get('title', '')}. {str(r.get('content', ''))[:200]}"
                     for _, r in work.iterrows()]
            embeddings = embedder(texts)

    seen = {}
    keep = []
    for pos, (idx, row) in enumerate(work.iterrows()):
        block = (str(row.get("region", "") or ""), _date_bucket(row, window_days))
        toks = _title_tokens(row.get("title", ""))
        emb = embeddings[pos] if embeddings is not None else None
        locs = _event_locations(row)

        is_dup = False
        for seen_toks, seen_emb, seen_locs in seen.get(block, []):
            if locs and seen_locs and locs.isdisjoint(seen_locs):
                continue
            if _jaccard(toks, seen_toks) >= threshold:
                is_dup = True
                break
            if emb is not None and seen_emb is not None \
                    and float(np.dot(emb, seen_emb)) >= embedding_threshold:
                is_dup = True
                break

        if not is_dup:
            seen.setdefault(block, []).append((toks, emb, locs))
            keep.append(idx)
            if max_results and len(keep) >= max_results:
                break
    return df.loc[keep].copy()


def is_article_too_old(published_date, max_days: int = 7) -> bool:
    """
    Returns True if the article is mathematically older than max_days.
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
            
            # Dashboard Schema Mapping
            "Render_Perp": format_list(all_perps),
            "Render_Target": format_list(article.get("ner_locations", [])),
            "Render_Casualties": format_casualties({
                "killed": article.get("casualties_killed", []),
                "injured": article.get("casualties_injured", []),
            }),
            
            "region": article.get("region"),
            "source_type": article.get("source_type"),
        }

        df = pd.DataFrame([row])
        url = row.get("url")

        if csv_path.exists():
            try:
                existing = pd.read_csv(csv_path)
            except Exception:
                existing = None
            if existing is not None and url and "url" in existing.columns \
                    and (existing["url"].astype(str) == str(url)).any():
                existing = existing[existing["url"].astype(str) != str(url)]
                combined = pd.concat([existing, df], ignore_index=True)
                combined.to_csv(csv_path, index=False)
            else:
                df.to_csv(csv_path, mode="a", header=False, index=False)
        else:
            df.to_csv(csv_path, mode="w", header=True, index=False)
            
    except Exception as e:
        print(f"⚠️ Failed to archive to historical: {e}")