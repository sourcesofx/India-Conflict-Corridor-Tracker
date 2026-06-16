"""
historical_purge.py  --  remove a set of URLs from the historical trend archive.

When an analyst marks an article "not relevant", clean_database drops it from the
live JSON lake. But the same article was archived to data/historical/YYYY/MM.csv
at scrape time (archive_to_historical), so it must be removed there too or it
keeps polluting 6-12 month trend analysis. This module is that removal pass.

Pure pandas / stdlib (no Streamlit). Dry-run by default; on write it backs up the
whole historical tree once (mirroring resync_historical's backup style), then
rewrites only the files that changed.

Caveat: this does not stop a future scrape from re-archiving the same URL; a
durable block-list would be a separate feature.
"""

import glob
import os
import shutil
from datetime import datetime

import pandas as pd


def _norm_url(u) -> str:
    """Match resync_historical: strip and drop a trailing slash."""
    if u is None:
        return ""
    try:
        if pd.isna(u):
            return ""
    except (TypeError, ValueError):
        pass
    return str(u).strip().rstrip("/")


def _resolve_hist_root(hist_root, data_root):
    if hist_root is not None:
        return str(hist_root)
    if data_root is None:
        try:
            from src.config import DATA_DIR
            data_root = os.path.dirname(str(DATA_DIR))
        except Exception:
            data_root = "data"
    return os.path.join(str(data_root), "historical")


def purge_historical(urls, hist_root=None, data_root=None,
                     write=False, backup_dir=None) -> dict:
    """Remove rows whose url is in `urls` from every historical CSV.

    Args:
        urls: iterable of URLs to remove.
        hist_root: path to the historical archive root (default: <data>/historical,
            derived from src.config.DATA_DIR when not given).
        data_root: alternative to hist_root -- the parent 'data' dir.
        write: False (default) previews only; True backs up then rewrites.
        backup_dir: explicit backup path (default: '<hist_root>_purge_backup_<ts>').

    Returns a summary dict. Never raises on the expected failure modes.
    """
    targets = {_norm_url(u) for u in urls}
    targets.discard("")

    result = {
        "urls_requested": len(targets),
        "files_scanned": 0,
        "files_changed": 0,
        "rows_removed": 0,
        "removed_by_file": {},
        "written": False,
        "backup_path": None,
        "error": None,
    }
    if not targets:
        return result  # nothing to remove

    hist_root = _resolve_hist_root(hist_root, data_root)
    if not os.path.isdir(hist_root):
        result["error"] = f"historical dir not found: {hist_root}"
        return result

    files = sorted(glob.glob(os.path.join(hist_root, "**", "*.csv"), recursive=True))
    result["files_scanned"] = len(files)

    planned = {}  # path -> reduced DataFrame
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if df.empty or "url" not in df.columns:
            continue
        mask = df["url"].map(_norm_url).isin(targets)
        n = int(mask.sum())
        if n > 0:
            planned[f] = df.loc[~mask].copy()
            result["rows_removed"] += n
            result["removed_by_file"][os.path.relpath(f, hist_root)] = n

    result["files_changed"] = len(planned)

    if not write or not planned:
        return result

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = backup_dir or f"{hist_root.rstrip(os.sep)}_purge_backup_{ts}"
    backup, n = base, 1
    while os.path.exists(backup):
        backup, n = f"{base}_{n}", n + 1
    shutil.copytree(hist_root, backup)
    result["backup_path"] = backup

    for f, ndf in planned.items():
        ndf.to_csv(f, index=False)
    result["written"] = True
    return result