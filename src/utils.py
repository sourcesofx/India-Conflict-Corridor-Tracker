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


def lexical_deduplicate(df: pd.DataFrame, max_results: int | None = None,
                        threshold: float = 0.5, window_days: int = 3,
                        use_embeddings: bool = True, embedding_threshold: float = 0.78,
                        embedder=None) -> pd.DataFrame:
    """
    Collapse duplicate reports of the same event. Within each region+time block,
    two articles are duplicates if EITHER:
      - their titles share enough words (Jaccard >= threshold), OR
      - their meanings are close (embedding cosine >= embedding_threshold).
    The second test catches the same event written with different words.
    Keeps the highest-scoring article of each cluster.
    """
    if df is None or df.empty:
        return df

    work = df.copy()
    if "final_risk_score" in work.columns:
        work = work.sort_values("final_risk_score", ascending=False, kind="stable")

    # Compute meaning-vectors for every title in one batch (optional layer).
    embeddings = None
    if use_embeddings:
        if embedder is None:
            embedder = _get_default_embedder()
        if embedder is not None:
            texts = [f"{r.get('title', '')}. {str(r.get('content', ''))[:200]}"
                     for _, r in work.iterrows()]
            embeddings = embedder(texts)

    seen = {}   # block -> list of (token_set, embedding_or_None)
    keep = []
    for pos, (idx, row) in enumerate(work.iterrows()):
        block = (str(row.get("region", "") or ""), _date_bucket(row, window_days))
        toks = _title_tokens(row.get("title", ""))
        emb = embeddings[pos] if embeddings is not None else None

        is_dup = False
        for seen_toks, seen_emb in seen.get(block, []):
            if _jaccard(toks, seen_toks) >= threshold:
                is_dup = True
                break
            if emb is not None and seen_emb is not None \
                    and float(np.dot(emb, seen_emb)) >= embedding_threshold:
                is_dup = True
                break

        if not is_dup:
            seen.setdefault(block, []).append((toks, emb))
            keep.append(idx)
            if max_results and len(keep) >= max_results:
                break
    return df.loc[keep].copy()


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
            "Render_Casualties": format_casualties({
                "killed": article.get("casualties_killed", []),
                "injured": article.get("casualties_injured", []),
            }),
            
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