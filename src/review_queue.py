"""
review_queue.py  --  data layer for the Review Queue tab (JSON-backed).

Pure pandas / standard-library logic (NO Streamlit, NO models) so it can be
unit-tested anywhere. Operates on the CANONICAL JSON lake (data/raw/*.json) --
the same store the dashboard and clean_database use -- so edits are durable.

  load_review_json        -> all articles as a DataFrame (+ needs_review_bool, _source_json)
  review_rows             -> just the flagged rows
  valid_tactics / tactic_to_incident / incident_for_tactic -> reclassify options
  save_correction_json    -> reclassify an article's tactic
  mark_not_relevant_json  -> flag manual_purge for clean_database to remove

Safety: the write functions are dry-run by default; with write=True they back up
the source JSON first, then mutate matching articles (by url) and rewrite the
file in the same json.dump style the scraper / clean_database use.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, List

import pandas as pd

DATA_DIR = Path("data/raw")
BACKUP_DIR = Path("data/review_queue_backups")


# --------------------------------------------------------------------------- #
#  Loader
# --------------------------------------------------------------------------- #
def _is_true(v: Any) -> bool:
    """needs_review may be a real bool (JSON) or the string 'True' (legacy)."""
    if v is True:
        return True
    return str(v).strip().lower() == "true"


def load_review_json(data_dir: Any = DATA_DIR) -> pd.DataFrame:
    """Read every data/raw/*.json into one DataFrame.

    - skips twitter files (as the scraper / clean_database do)
    - adds a real boolean column `needs_review_bool`
    - tags each row with `_source_json` so a write-back knows the file
    Returns an empty DataFrame if there are no JSON files.
    """
    data_dir = Path(data_dir)
    rows: List[dict] = []
    for json_file in sorted(data_dir.glob("*.json")):
        if "twitter" in json_file.name.lower():
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as fh:
                articles = json.load(fh)
        except Exception:
            continue
        if not isinstance(articles, list):
            continue
        for art in articles:
            if isinstance(art, dict):
                a = dict(art)
                a["_source_json"] = json_file.name
                rows.append(a)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "needs_review" in df.columns:
        df["needs_review_bool"] = df["needs_review"].apply(_is_true)
    else:
        df["needs_review_bool"] = False
    return df


def review_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Just the rows flagged for review (needs_review == True)."""
    if df.empty or "needs_review_bool" not in df.columns:
        return df.iloc[0:0] if not df.empty else df
    return df[df["needs_review_bool"]].copy()


# --------------------------------------------------------------------------- #
#  Tactic options for the reclassify dropdown (derived from tactic_classifier)
# --------------------------------------------------------------------------- #
_VIOLENT_GENERIC = "Armed Incident"   # assign_tactic VIOLENT fallback
_UNREST_GENERIC = "Civil Unrest"      # assign_tactic UNREST fallback (also a keyword tactic)
_ROUTINE_TACTIC = "Other"             # assign_tactic ROUTINE


def tactic_to_incident() -> "dict[str, str]":
    """Canonical map: granular_incident_type -> incident_type.

    Built from tactic_classifier's pattern lists so the keyword tactics never
    drift from what the classifier actually produces.
    """
    from src.tactic_classifier import (
        KINETIC_PATTERNS,
        UNREST_PATTERNS,
        COARSE_TO_INCIDENT,
    )

    mapping: "dict[str, str]" = {}
    for _pattern, tactic in KINETIC_PATTERNS:
        mapping[tactic] = COARSE_TO_INCIDENT["VIOLENT"]
    mapping[_VIOLENT_GENERIC] = COARSE_TO_INCIDENT["VIOLENT"]

    for _pattern, tactic in UNREST_PATTERNS:
        mapping[tactic] = COARSE_TO_INCIDENT["UNREST"]
    mapping[_UNREST_GENERIC] = COARSE_TO_INCIDENT["UNREST"]

    mapping[_ROUTINE_TACTIC] = COARSE_TO_INCIDENT["ROUTINE"]
    return mapping


def valid_tactics() -> "list[str]":
    """Ordered list of granular tactics for the reclassify dropdown."""
    return list(tactic_to_incident().keys())


def incident_for_tactic(tactic: str) -> str:
    """incident_type a given granular tactic must be saved with.

    Falls back to 'Other' for an unknown tactic rather than raising, so the
    Save path can never write an inconsistent pair.
    """
    return tactic_to_incident().get(tactic, "Other")


# --------------------------------------------------------------------------- #
#  JSON write layer  (operates on the canonical data/raw/*.json store)
#
#  save_correction_json   -> reclassify an article's tactic
#  mark_not_relevant_json -> flag manual_purge=True so clean_database purges it
#
#  Both: dry-run by default; with write=True the source JSON is backed up first,
#  then matching articles (by url) are mutated and the file rewritten with the
#  same json.dump style the scraper / clean_database use (indent=2, no ASCII
#  escaping). Setting needs_review=False drops the row from the queue.
# --------------------------------------------------------------------------- #
def _find_source_json(url: str, data_dir: Path):
    """Search every (non-twitter) JSON for the url; return the first match."""
    for path in sorted(Path(data_dir).glob("*.json")):
        if "twitter" in path.name.lower():
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                arts = json.load(fh)
        except Exception:
            continue
        if isinstance(arts, list) and any(
            isinstance(a, dict) and a.get("url") == url for a in arts
        ):
            return path
    return None


def _backup_file(path: Any, backup_dir: Any) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = Path(backup_dir) / ts
    bdir.mkdir(parents=True, exist_ok=True)
    dest = bdir / Path(path).name
    shutil.copy2(path, dest)
    return str(dest)


def _locate_and_load_json(url, source_json, data_dir, result):
    """Resolve the source JSON path + load it + count url matches.

    On any failure, fills result['error'] and returns (None, None, 0).
    On success returns (path, articles, n_matched).
    """
    data_dir = Path(data_dir)
    if source_json:
        path = data_dir / str(source_json)
        if not path.exists():
            result["error"] = f"source json not found: {path.name}"
            return None, None, 0
    else:
        path = _find_source_json(url, data_dir)
        if path is None:
            result["error"] = "url not found in any json"
            return None, None, 0
    result["source_json"] = path.name

    try:
        with open(path, "r", encoding="utf-8") as fh:
            articles = json.load(fh)
    except Exception as e:
        result["error"] = f"could not read {path.name}: {e}"
        return None, None, 0
    if not isinstance(articles, list):
        result["error"] = f"{path.name} is not a JSON array"
        return None, None, 0

    n = sum(1 for a in articles if isinstance(a, dict) and a.get("url") == url)
    result["found"] = n > 0
    result["n_matched"] = n
    if n == 0:
        result["error"] = f"url not present in {path.name}"
        return None, None, 0
    return path, articles, n


def _write_json(path: Any, articles: list) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(articles, fh, indent=2, ensure_ascii=False)


def save_correction_json(
    url: str,
    new_tactic: str,
    source_json: Any = None,
    data_dir: Any = DATA_DIR,
    write: bool = False,
    backup_dir: Any = BACKUP_DIR,
) -> dict:
    """Reclassify the article(s) with this url to new_tactic, in the JSON lake."""
    result: dict = {
        "url": url, "new_granular": new_tactic, "new_incident": None,
        "source_json": None, "found": False, "n_matched": 0,
        "old_granular": None, "old_incident": None, "old_needs_review": None,
        "written": False, "backup_path": None, "error": None,
    }

    if new_tactic not in valid_tactics():
        result["error"] = f"unknown tactic: {new_tactic!r}"
        return result
    result["new_incident"] = incident_for_tactic(new_tactic)

    path, articles, _ = _locate_and_load_json(url, source_json, data_dir, result)
    if path is None or articles is None:
        return result

    first = next(a for a in articles if isinstance(a, dict) and a.get("url") == url)
    result["old_granular"] = first.get("granular_incident_type")
    result["old_incident"] = first.get("incident_type")
    result["old_needs_review"] = first.get("needs_review")

    if not write:
        return result

    result["backup_path"] = _backup_file(path, backup_dir)
    for a in articles:
        if isinstance(a, dict) and a.get("url") == url:
            a["granular_incident_type"] = new_tactic
            a["incident_type"] = result["new_incident"]
            a["needs_review"] = False
    _write_json(path, articles)
    result["written"] = True
    return result


def mark_not_relevant_json(
    url: str,
    source_json: Any = None,
    data_dir: Any = DATA_DIR,
    write: bool = False,
    backup_dir: Any = BACKUP_DIR,
) -> dict:
    """Flag the article(s) with this url for purge by clean_database.

    Sets manual_purge=True and needs_review=False (so it leaves the queue). The
    actual removal happens on the next clean_database run; nothing is deleted
    here.
    """
    result: dict = {
        "url": url, "source_json": None, "found": False, "n_matched": 0,
        "title": None, "written": False, "backup_path": None, "error": None,
    }

    path, articles, _ = _locate_and_load_json(url, source_json, data_dir, result)
    if path is None or articles is None:
        return result

    first = next(a for a in articles if isinstance(a, dict) and a.get("url") == url)
    result["title"] = first.get("title")

    if not write:
        return result

    result["backup_path"] = _backup_file(path, backup_dir)
    for a in articles:
        if isinstance(a, dict) and a.get("url") == url:
            a["manual_purge"] = True
            a["needs_review"] = False
    _write_json(path, articles)
    result["written"] = True
    return result