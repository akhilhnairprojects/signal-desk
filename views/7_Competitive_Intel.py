"""Competitive Intel: what the network competitors are saying, and how
to counter it."""

import pandas as pd
import plotly.express as px
import streamlit as st

from src import competitors, config
from src.app_helpers import PLOTLY_LAYOUT, get_data, page_header

get_data()  # warm the shared cache so navigation stays snappy
page_header(
    "Competitive Intelligence",
    "The account universe excludes network competitors by design - this "
    "page tracks them instead. Nightly collection tags every competitor "
    "headline with a message theme; the matrix shows where each rival is "
    "loudest, and the battlecards pair their current messaging with our "
    "counter-positioning.",
)


@st.cache_data(show_spinner=False)
def get_competitor_news():
    return competitors.store.load("competitor_headlines")


heads = get_competitor_news()

if heads.empty:
    st.info(
        "No competitor headlines collected yet. Run "
        "`python scripts/collect_competitor_news.py` locally (or add "
        "`--limit 3` for a quick test), or trigger the nightly workflow "
        "from the repo's Actions tab - it collects these automatically "
        "every night.",
        icon=":material/rss_feed:",
    )
    st.stop()

covered = heads["account"].nunique()
c1, c2, c3 = st.columns(3)
c1.metric("Competitors tracked", len(config.COMPETITORS))
c2.metric("With recent coverage", covered)
c3.metric("Headlines on file", len(heads))

# -------------------------------------------------- Messaging activity map
st.subheader("Messaging activity matrix")
st.caption("Headline counts by competitor and theme over the last "
           f"{config.COMPETITOR_NEWS_LOOKBACK_DAYS} days - where each "
           "rival is putting its voice.")
matrix = competitors.theme_matrix(heads)
if not matrix.empty:
    fig = px.imshow(matrix, text_auto=True, aspect="auto",
                    color_continuous_scale=["#131A26", "#2E86D1"],
                    labels=dict(color="Headlines"))
    fig.update_layout(xaxis_title="", yaxis_title="",
                      height=110 + 34 * len(matrix),
                      coloraxis_showscale=False, **PLOTLY_LAYOUT)
    st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------- Battlecard
st.subheader("Battlecard")
pick = st.selectbox("Competitor",
                    sorted(heads["account"].unique().tolist()))
card = competitors.battlecard(pick, heads)

if not card["plays"]:
    st.caption("Not enough themed coverage for this competitor yet.")
else:
    st.markdown(f"Their three loudest themes right now, with our counter "
                f"for each ({card['headline_count']} headlines analysed):")
    rows = [{"Theme": p["theme"],
             "Their message (latest headline)": p["their_message"],
             "Our counter": p["our_counter"]} for p in card["plays"]]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                 column_config={
                     "Their message (latest headline)":
                         st.column_config.TextColumn(width="large"),
                     "Our counter": st.column_config.TextColumn(
                         width="large"),
                 })
    st.download_button(
        "Download battlecard (.md)",
        competitors.battlecard_markdown(card).encode(),
        file_name=f"battlecard_{pick.replace(' ', '_').lower()}.md",
        mime="text/markdown")

# ----------------------------------------------------------- Headline feed
st.subheader(f"Recent coverage: {pick}")
feed = (heads[heads["account"] == pick]
        .sort_values("published", ascending=False).head(15))
for _, h in feed.iterrows():
    st.markdown(f"- **{h['published']}** · `{h['theme']}` · "
                f"[{h['title']}]({h['link']})")

st.caption("Counter-positioning lines live in COUNTER_PLAYS in "
           "src/config.py - refine them as the team's messaging sharpens.")
