from src.review_queue import (
    load_review_json,
    review_rows,
    valid_tactics,
    save_correction_json,
    mark_not_relevant_json,
    incident_for_tactic,
)

_BLANKS = {"", "nan", "none", "[]", "{}"}


def _show(val) -> str:
    s = "" if val is None else str(val).strip()
    return s if s and s.lower() not in _BLANKS else "—"


def _rerun(st) -> None:
    fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if fn:
        fn()


def render_review_tab(st) -> None:
    st.subheader("🛡️ Review Queue")
    st.caption(
        "Articles the classifier flagged as uncertain. Reclassify them, or mark "
        "irrelevant noise for removal on the next database clean."
    )

    try:
        df = load_review_json()
    except Exception as e:
        st.error(f"Could not load the JSON lake: {e}")
        return

    if df.empty:
        st.info("No data found under data/raw/.")
        return

    rq = review_rows(df)
    c1, c2 = st.columns(2)
    c1.metric("Flagged for review", len(rq))
    c2.metric("Total articles", len(df))

    if len(rq) == 0:
        st.success("✅ Nothing awaiting review — the queue is clear.")
        return

    st.caption(
        "Tip: pause the scraper while reviewing so a concurrent scrape can't "
        "race a saved edit."
    )

    options = valid_tactics()

    for i, row in rq.iterrows():
        url = str(row.get("url", "") or "")
        src = row.get("_source_json")
        st.markdown("---")
        st.markdown(f"**{_show(row.get('title'))}**")
        st.caption(
            f"Source: {_show(row.get('source'))}  •  "
            f"Coarse: {_show(row.get('coarse_category'))}  •  "
            f"Confidence: {_show(row.get('tactic_confidence'))}  •  "
            f"Secondary: {_show(row.get('secondary_tactic'))}"
        )
        st.write(
            f"Current: **{_show(row.get('granular_incident_type'))}**  "
            f"(incident_type: {_show(row.get('incident_type'))})"
        )

        # --- reclassify ---
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            cur = str(row.get("granular_incident_type", "") or "").strip()
            idx = options.index(cur) if cur in options else 0
            choice = st.selectbox("Reclassify as", options, index=idx, key=f"rq_sel_{i}")
        with col_btn:
            st.write("")
            do_save = st.button("💾 Save", key=f"rq_save_{i}", use_container_width=True)

        if url:
            st.markdown(f"[🔗 Open original article]({url})")
        else:
            st.caption("⚠️ No url on this row — it can't be matched back to a file.")

        # --- not relevant (guarded) ---
        col_conf, col_del = st.columns([3, 1])
        with col_conf:
            confirm = st.checkbox("Confirm not relevant", key=f"rq_confirm_{i}")
        with col_del:
            st.write("")
            do_purge = st.button("🗑️ Not relevant", key=f"rq_notrel_{i}",
                                 use_container_width=True)

        # --- handle actions ---
        if do_save:
            if not url:
                st.error("Cannot save: this row has no url to match on.")
            else:
                res = save_correction_json(url, choice, source_json=src, write=True)
                if res.get("written"):
                    st.success(
                        f"Saved: {_show(res.get('old_granular'))} → {choice} "
                        f"(incident_type: {incident_for_tactic(choice)}).  "
                        f"Backup: {res.get('backup_path')}"
                    )
                    _rerun(st)
                else:
                    st.error(f"Save failed: {res.get('error') or 'unknown error'}")

        if do_purge:
            if not url:
                st.error("Cannot flag: this row has no url to match on.")
            elif not confirm:
                st.warning("Tick 'Confirm not relevant' before removing.")
            else:
                res = mark_not_relevant_json(url, source_json=src, write=True)
                if res.get("written"):
                    st.success(
                        "Flagged as not relevant — removed from the queue and "
                        "will be purged on the next clean_database run.  "
                        f"Backup: {res.get('backup_path')}"
                    )
                    _rerun(st)
                else:
                    st.error(f"Flag failed: {res.get('error') or 'unknown error'}")