"""AI-Ready Account Intelligence - portfolio overview page."""

import plotly.express as px
import streamlit as st

import json

from src import config, store
from src.app_helpers import (NEUTRAL, PLOTLY_LAYOUT, TIER_COLORS, get_data,
                             highlighted_segment, page_header,
                             segment_row_styler)

df, notes, meta = get_data()

page_header(
    "AI-Ready Account Intelligence",
    "Dynamic scoring and positioning across the enterprise account universe. "
    "Scores blend five public demand signals with field intelligence from the team.",
)

# ---------------------------------------------------------------- KPIs
# One number is the answer this page exists to give - how many accounts to
# call this week. The rest is context and is sized accordingly.
tier1 = int((df["tier"] == "Tier 1").sum())
fresh_news = int((df["news_score"] > 0).sum())

hero, c2, c3, c4 = st.columns([1.4, 1, 1, 1])
with hero:
    with st.container(key="hero-metric"):
        st.metric("Tier 1 · engage now", tier1,
                  help="The top 15% of the universe by adjusted score. "
                       "Tier boundaries are quantiles, so this stays a "
                       "callable list as scores move.")
c2.metric("Accounts tracked", len(df))
c3.metric("Industries", df["industry"].nunique())
c4.metric("Tier 1 score floor",
          f"{df.loc[df['tier'] == 'Tier 1', 'adjusted_score'].min():.0f}",
          help="What an account currently has to score to make the "
               "callable list. Scores are percentiles, so an average score "
               "would always read ~50 and tell you nothing.")

custom_n = int((df["source"] == "custom").sum())
st.caption(f"{len(notes)} field notes · {fresh_news} accounts with AI news "
           f"in the last 30d · Storage: {store.backend_label()}"
           + f" · Signal weights: {meta.get('weights_source', 'configured')}"
           + f" · Segments: {meta.get('segmentation_source', 'computed')}"
           + (f" · {custom_n} user-added companies in the universe"
              if custom_n else ""))

changes_path = config.RESULTS_DIR / "tier_changes.json"
if changes_path.exists():
    changes = json.loads(changes_path.read_text()).get("changes", [])
    if changes:
        moves = ", ".join(f"**{c['account']}** {c['from']} → {c['to']}"
                          for c in changes[:5])
        extra = f" (+{len(changes) - 5} more)" if len(changes) > 5 else ""
        st.info(f"Since the last refresh, {len(changes)} account(s) "
                f"changed tier: {moves}{extra}",
                icon=":material/trending_up:")

st.divider()

# --------------------------------------------------------- Weekly digest
digest_path = config.RESULTS_DIR / "weekly_digest.json"
if digest_path.exists():
    digest = json.loads(digest_path.read_text())

    def _clean(entries, value_key):
        """Drop empty/NaN digest rows so only real companies render."""
        out = []
        for m in entries or []:
            name, val = m.get("account"), m.get(value_key)
            if (isinstance(name, str) and name.strip()
                    and name.lower() != "nan"
                    and isinstance(val, (int, float)) and val == val):
                out.append(m)
        return out

    top_news = _clean(digest.get("top_news"), "news_score")
    top_movers = _clean(digest.get("top_movers"), "delta")
    with st.expander(f"Weekly digest - generated {digest['generated_at'][:10]}",
                     expanded=False):
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Notes added (7d)", digest["notes_last_7d"])
        d2.metric("KB edits (7d)", digest["kb_edits_last_7d"])
        d3.metric("User-added companies", digest["custom_accounts"])
        d4.metric("Accounts with fresh news", digest["news_coverage"])
        if top_news:
            st.markdown("**Top news momentum this week:** " + ", ".join(
                f"{m['account']} ({m['news_score']})" for m in top_news))
        if top_movers:
            st.markdown("**Biggest score movements vs base:** " + ", ".join(
                f"{m['account']} ({m['delta']:+.1f})" for m in top_movers))
        if not top_news and not top_movers:
            st.caption("No score-moving activity recorded this week.")
else:
    st.caption("The weekly digest appears here after the first Friday-night "
               "sync (or run scripts/weekly_sync.py).")

# ------------------------------------------------- Tier and industry views
left, right = st.columns([2, 3])

with left:
    st.subheader("Tier distribution")
    st.caption("Click a bar to cross-filter this page to that tier; "
               "click it again to clear.")
    tier_counts = (
        df["tier"].value_counts().rename_axis("tier").reset_index(name="accounts")
    ).sort_values("tier")
    tier_counts["action"] = tier_counts["tier"].map(config.TIER_DESCRIPTIONS)
    fig = px.bar(
        tier_counts, x="tier", y="accounts", color="tier",
        color_discrete_map=TIER_COLORS, text="accounts",
        custom_data=["tier"],
        hover_data={"action": True, "tier": False},
    )
    fig.update_layout(showlegend=False, **PLOTLY_LAYOUT)
    tier_event = st.plotly_chart(fig, width="stretch", key="tier_filter",
                                 on_select="rerun")

# The tier clicked in the chart (if any) drives every chart and table below.
selected_tier = None
try:
    points = tier_event.selection.points
    if points:
        cdata = points[0].get("customdata") or []
        selected_tier = cdata[0] if cdata else points[0].get("x")
except Exception:
    selected_tier = None

view = df if selected_tier is None else df[df["tier"] == selected_tier]

with right:
    st.subheader("Average score by industry"
                 + (f" — {selected_tier}" if selected_tier else ""))
    by_ind = (
        view.groupby("industry")["adjusted_score"].mean().round(1)
        .sort_values().reset_index()
    )
    fig = px.bar(
        by_ind, x="adjusted_score", y="industry", orientation="h",
        color_discrete_sequence=[NEUTRAL], text="adjusted_score",
    )
    fig.update_layout(xaxis_title="", yaxis_title="", **PLOTLY_LAYOUT)
    st.plotly_chart(fig, width="stretch")

if selected_tier:
    st.info(f"Cross-filter active: the industry chart and the table "
            f"below show **{selected_tier} only** ({len(view)} accounts). "
            f"Click the {selected_tier} bar again to clear. The headline "
            "KPIs above always show the whole portfolio.",
            icon=":material/filter_alt:")

# ------------------------------------------------------- Priority accounts
st.subheader("Top priority accounts"
             + (f" — {selected_tier}" if selected_tier else ""))
st.caption(
    "Ranked by adjusted score (signal model + field notes + news momentum). "
    "Use the Account Explorer page for filtering and detail."
)

top = view.sort_values("adjusted_score", ascending=False).head(15)
top_cols = top[["account", "industry", "sub_industry", "adjusted_score",
                "tier", "segment", "note_count"]]
hl_segment = highlighted_segment()
st.dataframe(
    segment_row_styler(top_cols, hl_segment) if hl_segment else top_cols,
    width="stretch",
    hide_index=True,
    column_config={
        "account": "Account",
        "industry": "Industry",
        "sub_industry": "Sub-industry",
        "adjusted_score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%.0f",
        ),
        "tier": "Tier",
        "segment": "Segment",
        "note_count": st.column_config.NumberColumn("Notes", format="%d"),
    },
)
if hl_segment:
    st.caption(f"Shaded rows belong to the highlighted segment "
               f"'{hl_segment}' (set on the Segments page).")

with st.expander("About this model"):
    st.markdown(
        f"""
**The score is a percentile, not a rating.** Each of the five demand signals
is ranked across the universe first, then weighted
({", ".join(f"{v:.1%} {config.SIGNAL_LABELS[k]}" for k, v in config.SIGNAL_WEIGHTS.items())}).
Ranking first puts every signal on the same distribution, so a weight is a
statement about how much that signal should matter rather than an artefact of
its spread — on raw values Cloud Presence sat at a nominal 20% and contributed
12.2% of score variance, while Global Footprint was also 20% and contributed
24.9%.

AI Hiring and AI Announcements correlate at **r = 0.94** across this universe,
so they split one 35% AI allocation rather than counting as two independent
signals.

**Tiers are quantiles** — Tier 1 is the top 15% — so the shortlist stays a
callable size as scores drift. Fixed cutoffs had put 29% of the universe in
"engage now".

Segments come from K-Means on the standardised signals
(k = {meta['k']}, silhouette = {meta['silhouette']}). Field notes adjust
scores by ±{config.IMPACT_POINTS['Positive']} points each, capped at
±{config.MAX_ADJUSTMENT}, and recent AI news adds up to
+{config.MAX_NEWS_ADJUSTMENT} points of momentum (see the **News Monitor**
page). Weights switch from configured to learned once enough engagement
outcomes are logged. Every tunable rule lives in `src/config.py`;
the full analysis is in `docs/scoring-model.md`.
"""
    )
