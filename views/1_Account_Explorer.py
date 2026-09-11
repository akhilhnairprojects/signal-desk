"""Account Explorer: filter, drill in, compare, and trace every score."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config, outcomes, similarity
from src.app_helpers import (PLOTLY_LAYOUT, PRIMARY, SEGMENT_COLORS,
                             get_data, get_kb, get_news, highlighted_segment,
                             page_header, refresh_data,
                             segment_highlight_selector, segment_row_styler)

df, notes, _ = get_data()
kb = get_kb()
_, headlines = get_news()
page_header("Account Explorer",
            "Filter the universe, open an account's full profile, and compare "
            "accounts side by side.")

SIGNALS = list(config.SIGNAL_WEIGHTS)
LABELS = [config.SIGNAL_LABELS[s] for s in SIGNALS]

# ------------------------------------------------------------- Filters
with st.sidebar:
    st.header("Filters")
    industries = st.multiselect("Industry", sorted(df["industry"].unique()))
    tiers = st.multiselect("Tier", ["Tier 1", "Tier 2", "Tier 3"])
    segments = st.multiselect("Segment", sorted(df["segment"].unique()))
    score_min, score_max = st.slider("Score range", 0, 100, (0, 100))
    only_custom = st.checkbox("Only user-added companies")
    search = st.text_input("Search account name")
    st.divider()
    segment_highlight_selector(sorted(df["segment"].unique()))

view = df.copy()
if industries:
    view = view[view["industry"].isin(industries)]
if tiers:
    view = view[view["tier"].isin(tiers)]
if segments:
    view = view[view["segment"].isin(segments)]
if only_custom:
    view = view[view["source"] == "custom"]
view = view[view["adjusted_score"].between(score_min, score_max)]
if search:
    view = view[view["account"].str.contains(search, case=False)]

st.caption(f"{len(view)} of {len(df)} accounts match the current filters.")
hl = highlighted_segment()
explorer_table = (view[["account", "ticker", "industry", "sub_industry",
                        "adjusted_score", "tier", "segment", "source"]]
                  .sort_values("adjusted_score", ascending=False))
st.dataframe(
    segment_row_styler(explorer_table, hl) if hl else explorer_table,
    width="stretch", hide_index=True, height=320,
    column_config={
        "account": "Account", "ticker": "Ticker", "industry": "Industry",
        "sub_industry": "Sub-industry",
        "adjusted_score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%.0f"),
        "tier": "Tier", "segment": "Segment",
        "source": st.column_config.TextColumn(
            "Source", help="baseline = original universe, "
                           "custom = added and auto-researched in-app"),
    },
)

st.divider()

# ------------------------------------------------------- Account detail
st.subheader("Account profile")
options = view["account"].sort_values().tolist() or df["account"].sort_values().tolist()
selected = st.selectbox("Select an account", options)
row = df[df["account"] == selected].iloc[0]

info, viz = st.columns([2, 3])

with info:
    st.markdown(f"### {row['account']}  \n"
                f"{row['industry']} · {row['sub_industry']} "
                f"{'· ' + row['ticker'] if row['ticker'] else ''}")
    total_adj = row["enrichment_adj"] + row["news_adj"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Adjusted score", f"{row['adjusted_score']:.0f}",
              delta=f"{total_adj:+.1f} vs base" if total_adj else None,
              help="Base signal score plus enrichment and news adjustments")
    m2.metric("Tier", row["tier"], help=row["tier_action"])
    m3.metric("Segment", row["segment"])
    if row.get("measured_signals"):
        st.caption(f"Measured signals in this profile: "
                   f"{row['measured_signals']} - evidence has replaced "
                   "the estimate for those signals.")
    if row["source"] == "custom":
        st.caption("User-added company, auto-researched. See the "
                   "Add a Company page for its research rationale.")

    acct_notes = notes[notes["account"] == selected]
    acct_kb = kb[kb["account"] == selected] if not kb.empty else kb
    st.markdown(f"**Field notes ({len(acct_notes)}) · "
                f"KB articles ({len(acct_kb)})**")
    if acct_notes.empty and acct_kb.empty:
        st.caption("No enrichment yet - add notes or KB articles on the "
                   "Knowledge Base page.")
    for _, n in acct_notes.sort_values("date", ascending=False).head(4).iterrows():
        st.markdown(f"- *{n['date']}* · **{n['category']}** ({n['impact']}) - "
                    f"{n['note']}")

    with st.expander("Engagement outcomes"):
        st.caption("Ground truth for the model: once enough outcomes are "
                   "logged, scripts/train_weights.py learns the signal "
                   "weights from them.")
        history = outcomes.account_outcomes(selected)
        if not history.empty:
            st.dataframe(history[["date", "outcome", "amount", "note"]],
                         width="stretch", hide_index=True, height=140)
        with st.form(f"outcome_{selected}", clear_on_submit=True):
            o1, o2 = st.columns(2)
            out_type = o1.selectbox("Outcome", config.OUTCOME_TYPES)
            out_amount = o2.text_input("Deal size (optional)",
                                       placeholder="e.g. 250k")
            out_note = st.text_input("Context (optional)")
            out_by = st.text_input("Logged by (optional)")
            logged = st.form_submit_button("Log outcome")
        if logged:
            outcomes.log_outcome(selected, out_type, out_amount,
                                 out_note, out_by)
            refresh_data()
            st.success(f"{out_type} logged for {selected}.")
            st.rerun()


with viz:
    tab_radar, tab_breakdown = st.tabs(["Signal profile", "Score breakdown"])
    with tab_radar:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[df[s].mean() for s in SIGNALS], theta=LABELS,
            fill="toself", name="Portfolio average",
            line=dict(color="#B0BEC5")))
        fig.add_trace(go.Scatterpolar(
            r=[row[s] for s in SIGNALS], theta=LABELS,
            fill="toself", name=row["account"],
            line=dict(color=PRIMARY)))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])),
                          **PLOTLY_LAYOUT)
        st.plotly_chart(fig, width="stretch")

    with tab_breakdown:
        # The scoring methodology, visualised: how this account's number
        # is built from base + decayed enrichment + news.
        fig = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "relative", "relative", "total"],
            x=["Base signals", "Field notes", "Knowledge base",
               "News momentum", "Final score"],
            y=[row["base_score"], row["note_adj"], row["kb_adj"],
               row["news_adj"], 0],
            text=[f"{row['base_score']:.1f}", f"{row['note_adj']:+.1f}",
                  f"{row['kb_adj']:+.1f}", f"{row['news_adj']:+.1f}",
                  f"{row['adjusted_score']:.1f}"],
            textposition="outside",
            connector=dict(line=dict(color="#B0BEC5")),
            increasing=dict(marker=dict(color="#2E7D32")),
            decreasing=dict(marker=dict(color="#C62828")),
            totals=dict(marker=dict(color=PRIMARY)),
        ))
        fig.update_layout(showlegend=False,
                          yaxis=dict(range=[0, 108], title="Score"),
                          **PLOTLY_LAYOUT)
        st.plotly_chart(fig, width="stretch")
        st.caption("Enrichment carries full weight for 6 months, then halves "
                   f"every {config.DECAY_HALF_LIFE_DAYS} days. Combined "
                   f"enrichment is capped at ±{config.MAX_ADJUSTMENT}; news "
                   f"adds up to +{config.MAX_NEWS_ADJUSTMENT}.")

# ---------------------------------------------------------- Similar accounts
st.subheader("Similar accounts")
DIST_HELP = ("Euclidean distance in standardised signal space: each of the "
             "five demand signals is converted to a z-score, and the "
             "distance is the straight-line gap between the two accounts in "
             "that 5-dimensional space. 0 = identical profile; each unit is "
             "roughly one standard deviation of difference.")
st.caption("The selected account is pinned on top; nearest signal-profile "
           "neighbours follow. Hover the Distance column header for the "
           "exact definition of the metric.")

pinned = pd.DataFrame([{
    "account": f"{row['account']}  (selected)",
    "industry": row["industry"], "base_score": row["base_score"],
    "tier": row["tier"], "similarity_distance": 0.0,
}])
similar = similarity.similar_accounts(df, selected)
sim_table = pd.concat([pinned, similar], ignore_index=True)
st.dataframe(
    sim_table, width="stretch", hide_index=True,
    column_config={
        "account": "Account", "industry": "Industry",
        "base_score": st.column_config.NumberColumn("Score", format="%.0f"),
        "tier": "Tier",
        "similarity_distance": st.column_config.NumberColumn(
            "Distance", format="%.2f", help=DIST_HELP),
    },
)

# ------------------------------------------------------ Compare accounts
st.divider()
st.subheader("Compare accounts side by side")
compare = st.multiselect(
    "Pick 2-4 accounts",
    df["account"].sort_values().tolist(),
    default=[selected],
    max_selections=4,
)
if len(compare) >= 2:
    comp = df[df["account"].isin(compare)]
    fig = go.Figure()
    for i, (_, r) in enumerate(comp.iterrows()):
        fig.add_trace(go.Scatterpolar(
            r=[r[s] for s in SIGNALS], theta=LABELS, fill="toself",
            name=r["account"], opacity=0.75,
            line=dict(color=SEGMENT_COLORS[i % len(SEGMENT_COLORS)])))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])),
                      **PLOTLY_LAYOUT)
    st.plotly_chart(fig, width="stretch")

    table = comp.set_index("account")[
        SIGNALS + ["base_score", "note_adj", "kb_adj", "news_adj",
                   "adjusted_score", "tier", "segment"]].T
    table.index = LABELS + ["Base score", "Field notes adj", "KB adj",
                            "News adj", "Adjusted score", "Tier", "Segment"]
    st.dataframe(table, width="stretch")
else:
    st.caption("Add at least one more account to compare.")

# ------------------------------------------------------- Recent AI news
acct_news = headlines[headlines["account"] == selected] if not headlines.empty else headlines
if not acct_news.empty:
    st.subheader("Recent AI news")
    for _, h in acct_news.sort_values("published", ascending=False).head(5).iterrows():
        st.markdown(f"- **{h['published']}** · [{h['title']}]({h['link']})")
