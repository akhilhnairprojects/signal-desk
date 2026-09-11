"""Add a Company: dynamic account addition with automatic research."""

import streamlit as st

from src import config, ingest, research, store
from src.app_helpers import get_data, page_header, refresh_data

df, _, _ = get_data()
page_header(
    "Add a Company",
    "Type a company name and the platform researches it automatically: it "
    "starts from the industry's baseline signal profile, pulls the "
    "company's recent news, adjusts the signals from that evidence, and "
    "adds the account to the universe - scored, tiered, segmented, and "
    "visible everywhere like any other account.",
)
st.caption(f"Storage: {store.backend_label()}")

baseline = ingest.load_baseline_only()

# --------------------------------------------------------------- Research
with st.form("research_form"):
    c1, c2, c3 = st.columns([2, 2, 2])
    name = c1.text_input("Company name", placeholder="e.g. Vertex Grocers")
    industry = c2.selectbox(
        "Industry (sets the baseline)",
        sorted(baseline["industry"].unique()),
        help="The research starts from this industry's average signal "
             "profile, learned from the existing universe, then adjusts "
             "it with news evidence.")
    subs = sorted(baseline.loc[baseline["industry"] == industry,
                               "sub_industry"].unique()) if industry else []
    sub_industry = c3.selectbox("Sub-industry (optional)", ["", *subs])
    added_by = st.text_input("Added by", placeholder="Your name / role")
    run = st.form_submit_button("Research this company", type="primary")

if run:
    clean = name.strip()
    if not clean:
        st.warning("Enter a company name first.")
    elif clean in config.EXCLUDED_ACCOUNTS:
        st.warning(f"{clean} is excluded from this universe by design "
                   "(see src/config.py).")
    elif clean.lower() in set(df["account"].str.lower()):
        st.warning(f"{clean} is already in the universe - open it in the "
                   "Account Explorer instead.")
    else:
        with st.spinner(f"Researching {clean}: industry baseline + recent "
                        "news evidence..."):
            profile = research.research_company(
                clean, baseline, industry=industry,
                sub_industry=sub_industry or None)
        st.session_state["pending_profile"] = profile
        st.session_state["pending_added_by"] = added_by

# ------------------------------------------------------ Review and confirm
profile = st.session_state.get("pending_profile")
if profile:
    st.divider()
    st.subheader(f"Research results: {profile['account']}")

    cols = st.columns(5)
    for col, sig in zip(cols, config.SIGNAL_WEIGHTS):
        col.metric(config.SIGNAL_LABELS[sig], profile[sig])

    st.markdown("**How these numbers were produced**")
    st.info(profile["rationale"])

    if profile.get("articles"):
        with st.expander(f"News evidence ({len(profile['articles'])} articles)"):
            for a in profile["articles"][:10]:
                st.markdown(f"- {a['published'].date()} · "
                            f"[{a['title']}]({a['link']})")
    else:
        st.caption("No recent coverage found - the profile rests on the "
                   "industry baseline, which is exactly how the original "
                   "universe was constructed. The nightly news job will "
                   "keep watching for coverage.")

    left, right = st.columns(2)
    if left.button("Add to the account universe", type="primary"):
        research.add_company(profile,
                             st.session_state.get("pending_added_by", ""))
        refresh_data()
        del st.session_state["pending_profile"]
        st.success(f"{profile['account']} added. It is now scored, tiered "
                   "and segmented across the whole platform, and the "
                   "nightly news job will refresh it automatically.")
        st.rerun()
    if right.button("Discard"):
        del st.session_state["pending_profile"]
        st.rerun()

# ------------------------------------------------------ Manage custom list
st.divider()
st.subheader("User-added companies")
custom = df[df["source"] == "custom"]
if custom.empty:
    st.caption("None yet.")
else:
    st.dataframe(
        custom[["account", "industry", "sub_industry", "adjusted_score",
                "tier", "segment", "last_updated"]]
        .sort_values("adjusted_score", ascending=False),
        width="stretch", hide_index=True,
        column_config={"adjusted_score": st.column_config.NumberColumn(
            "Score", format="%.0f")})
    to_remove = st.selectbox("Remove a company",
                             ["-"] + custom["account"].tolist())
    if to_remove != "-" and st.button(f"Remove {to_remove}"):
        research.remove_company(to_remove)
        refresh_data()
        st.rerun()
