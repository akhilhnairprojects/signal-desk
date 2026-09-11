"""Knowledge Base & Enrichment: notes and articles, editable in-app."""

import streamlit as st

import pandas as pd

from src import config, enrich, store
from src.app_helpers import get_data, get_kb, page_header, refresh_data

df, notes, _ = get_data()
kb = get_kb()
page_header(
    "Knowledge Base & Enrichment",
    "Everything the team knows about an account lives here: quick field "
    "notes and longer-lived KB articles, both editable in the app and both "
    "feeding the score with time-decayed weight.",
)
st.caption(f"Storage: {store.backend_label()}")

tab_notes, tab_kb = st.tabs(["Field notes", "Knowledge base articles"])

# ================================================================== NOTES
with tab_notes:
    form_col, log_col = st.columns([2, 3])

    with form_col:
        st.subheader("Add a note")
        with st.form("note_form", clear_on_submit=True):
            account = st.selectbox("Account", df["account"].sort_values())
            author = st.text_input("Your name / role",
                                   placeholder="e.g. AM, Northeast")
            category = st.selectbox("Category", config.NOTE_CATEGORIES)
            impact = st.radio(
                "Impact on priority", ["Positive", "Neutral", "Negative"],
                horizontal=True,
                help=f"±{config.IMPACT_POINTS['Positive']} points, decaying "
                     f"after {config.DECAY_START_DAYS} days; combined "
                     f"enrichment capped at ±{config.MAX_ADJUSTMENT}.")
            note = st.text_area("Note", placeholder="What did you learn?")
            submitted = st.form_submit_button("Save note", type="primary")

        if submitted:
            if not note.strip():
                st.warning("Write the note before saving.")
            else:
                enrich.append_note(account, author, category, impact, note)
                refresh_data()
                st.success(f"Note saved for {account}. Scores refreshed.")
                st.rerun()

    with log_col:
        st.subheader("Notes log")
        st.caption("Every note - seeded or user-written - is editable "
                   "inline: click any cell to change it, use the row "
                   "checkboxes + Delete to remove notes, or add a row at "
                   "the bottom. Nothing is stored until you press Save.")
        if notes.empty:
            st.caption("No notes yet.")
        else:
            f1, f2 = st.columns(2)
            acct_f = f1.multiselect("Filter by account",
                                    sorted(notes["account"].unique()))
            cat_f = f2.multiselect("Filter by category",
                                   config.NOTE_CATEGORIES)
            log = notes.copy()
            if acct_f:
                log = log[log["account"].isin(acct_f)]
            if cat_f:
                log = log[log["category"].isin(cat_f)]
            log["weight_today"] = log["date"].map(enrich.current_weight)

            edited = st.data_editor(
                log.sort_values("date", ascending=False),
                width="stretch", height=340, num_rows="dynamic",
                disabled=["weight_today"], key="notes_editor",
                column_config={
                    "date": st.column_config.TextColumn(
                        "Date", help="YYYY-MM-DD - editing the date moves "
                                     "the note along the decay curve"),
                    "account": st.column_config.SelectboxColumn(
                        "Account", options=df["account"].sort_values().tolist(),
                        required=True),
                    "author": st.column_config.TextColumn("Author"),
                    "category": st.column_config.SelectboxColumn(
                        "Category", options=config.NOTE_CATEGORIES,
                        required=True),
                    "impact": st.column_config.SelectboxColumn(
                        "Impact", options=["Positive", "Neutral", "Negative"],
                        required=True),
                    "note": st.column_config.TextColumn("Note"),
                    "weight_today": st.column_config.NumberColumn(
                        "Weight now", format="%.2f",
                        help="Time-decay factor applied today. 1.00 for the "
                             "first 6 months, then halves every "
                             f"{config.DECAY_HALF_LIFE_DAYS} days. "
                             "Recomputed on save."),
                })

            if st.button("Save note changes", type="primary"):
                cols = store.TABLES["notes"]
                full = notes.copy()
                # Rows deleted in the editor (only visible rows can be)
                deleted = log.index.difference(edited.index)
                full = full.drop(index=deleted, errors="ignore")
                # Edits to existing rows
                keep = edited.index.intersection(full.index)
                full.loc[keep, cols] = edited.loc[keep, cols]
                # Rows added at the bottom of the editor
                added = edited.loc[edited.index.difference(log.index), cols]
                added = added[added["note"].astype(str).str.strip() != ""]
                if not added.empty:
                    added["date"] = added["date"].replace(
                        "", pd.Timestamp.today().date().isoformat())
                    full = pd.concat([full, added], ignore_index=True)
                store.replace_table("notes", full.reset_index(drop=True))
                refresh_data()
                st.success("Notes saved - scores refreshed.")
                st.rerun()

            st.download_button("Download notes.csv",
                               notes.to_csv(index=False).encode(),
                               file_name="notes.csv", mime="text/csv")

# ============================================================ KB ARTICLES
with tab_kb:
    list_col, edit_col = st.columns([2, 3])

    with list_col:
        st.subheader("Articles")
        if kb.empty:
            st.caption("No articles yet - create the first one on the right.")
            titles = []
        else:
            kb_view = kb.copy()
            kb_view["weight_today"] = kb_view["updated_at"].map(
                enrich.current_weight)
            st.dataframe(
                kb_view[["account", "title", "impact", "updated_at",
                         "weight_today"]].sort_values("updated_at",
                                                      ascending=False),
                width="stretch", hide_index=True, height=300,
                column_config={
                    "account": "Account", "title": "Title",
                    "impact": "Impact",
                    "updated_at": st.column_config.TextColumn("Last updated"),
                    "weight_today": st.column_config.NumberColumn(
                        "Weight now", format="%.2f",
                        help="Editing an article resets its decay clock - "
                             "reviewed knowledge counts as fresh."),
                })
            titles = (kb["account"] + " — " + kb["title"]).tolist()

    with edit_col:
        st.subheader("Create or edit an article")
        st.caption("Select an existing article to edit it in place - no "
                   "downloading, no redeploys - or leave it on 'New "
                   "article' to write one.")
        choice = st.selectbox("Article", ["New article"] + sorted(titles))

        if choice == "New article":
            initial = {"account": None, "title": "", "content": "",
                       "author": "", "impact": "Neutral"}
        else:
            acct, title = choice.split(" — ", 1)
            match = kb[(kb["account"] == acct) & (kb["title"] == title)].iloc[0]
            initial = {"account": acct, "title": title,
                       "content": match["content"],
                       "author": match["author"], "impact": match["impact"]}

        accounts = df["account"].sort_values().tolist()
        acct_idx = (accounts.index(initial["account"])
                    if initial["account"] in accounts else 0)
        with st.form("kb_form"):
            kb_account = st.selectbox("Account", accounts, index=acct_idx)
            kb_title = st.text_input("Title", value=initial["title"])
            kb_content = st.text_area("Content", value=initial["content"],
                                      height=220)
            kb_author = st.text_input("Author", value=initial["author"])
            kb_impact = st.radio(
                "Impact on priority", ["Positive", "Neutral", "Negative"],
                index=["Positive", "Neutral", "Negative"].index(
                    initial["impact"] if initial["impact"] in
                    ("Positive", "Neutral", "Negative") else "Neutral"),
                horizontal=True,
                help=f"KB articles carry ±{config.KB_IMPACT_POINTS['Positive']} "
                     "point each, with the same decay and cap as notes.")
            saved = st.form_submit_button("Save article", type="primary")

        if saved:
            if not kb_title.strip() or not kb_content.strip():
                st.warning("Both a title and content are required.")
            else:
                enrich.save_kb_article(kb_account, kb_title, kb_content,
                                       kb_author, kb_impact)
                refresh_data()
                st.success("Article saved. Its decay clock starts now.")
                st.rerun()

        if choice != "New article":
            if st.button("Delete this article"):
                enrich.delete_kb_article(initial["account"], initial["title"])
                refresh_data()
                st.rerun()

# ------------------------------------------------- accounts moved by both
st.divider()
st.subheader("Accounts moved by enrichment")
moved = df[df["enrichment_adj"] != 0][
    ["account", "industry", "base_score", "note_adj", "kb_adj",
     "enrichment_adj", "adjusted_score", "tier"]
].sort_values("enrichment_adj", ascending=False)
if moved.empty:
    st.caption("No score adjustments yet.")
else:
    st.dataframe(
        moved, width="stretch", hide_index=True,
        column_config={
            "account": "Account", "industry": "Industry",
            "base_score": st.column_config.NumberColumn("Base", format="%.0f"),
            "note_adj": st.column_config.NumberColumn("Notes", format="%+.1f"),
            "kb_adj": st.column_config.NumberColumn("KB", format="%+.1f"),
            "enrichment_adj": st.column_config.NumberColumn(
                "Combined", format="%+.1f"),
            "adjusted_score": st.column_config.NumberColumn(
                "Adjusted", format="%.0f"),
            "tier": "Tier",
        })
