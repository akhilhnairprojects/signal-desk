"""News Monitor: the live signal feeding the scoring model."""

import streamlit as st

from src import config, news
from src.app_helpers import get_data, get_news, page_header

df, _, _ = get_data()
signals, headlines = get_news()
page_header(
    "News Monitor",
    "AI-related coverage per account from Google News, refreshed nightly. Fresh momentum adds up to "
    f"+{config.MAX_NEWS_ADJUSTMENT} points to an account's score; "
    "silence stays neutral.",
)

last = news.last_collected(signals)
covered = int((signals["news_score"] > 0).sum()) if not signals.empty else 0

c1, c2, c3 = st.columns(3)
c1.metric("Last collection", last[:16].replace("T", " ") + " UTC" if last else "Never")
c2.metric("Accounts with recent coverage", covered)
c3.metric("Headlines on file", len(headlines))

# ----------------------------------------------------------- empty state
if signals.empty or covered == 0:
    st.info(
        "No news signals collected yet. Run "
        "`python scripts/collect_news.py` locally (about 3-4 minutes for "
        "all accounts, or add `--limit 15` for a quick test), then re-run "
        "the pipeline. Once the project is on GitHub, the nightly "
        "workflow in `.github/workflows/news.yml` does this automatically - or trigger it from any browser via the repo's "
        "Actions tab.",
        icon=":material/rss_feed:",
    )

# ------------------------------------------------- Accounts moved by news
selected_account = None
if not signals.empty and covered > 0:
    st.subheader("Accounts currently moved by news")
    st.caption("Click any row to jump straight to that account's live "
               "headlines below - the search runs automatically.")
    merged = signals.merge(
        df[["account", "industry", "adjusted_score", "tier"]],
        on="account", how="inner",
    )
    moved = (merged[merged["news_adj"] > 0]
             .sort_values("news_adj", ascending=False)
             [["account", "industry", "article_count", "news_adj",
               "adjusted_score", "tier"]]
             .reset_index(drop=True))
    table_event = st.dataframe(
        moved,
        width="stretch", hide_index=True,
        key="news_moved", on_select="rerun", selection_mode="single-row",
        column_config={
            "account": "Account", "industry": "Industry",
            "article_count": st.column_config.NumberColumn(
                "Articles (30d)", format="%d"),
            "news_adj": st.column_config.NumberColumn(
                "Score boost", format="+%.1f"),
            "adjusted_score": st.column_config.NumberColumn(
                "Adjusted score", format="%.0f"),
            "tier": "Tier",
        },
    )
    try:
        picked_rows = table_event.selection.rows
        if picked_rows:
            selected_account = moved.iloc[picked_rows[0]]["account"]
    except Exception:
        selected_account = None

# --------------------------------------------------- On-demand live check
st.divider()
st.subheader("Live check")
st.caption("Fetch this moment's headlines for one account without waiting "
           "for the next scheduled collection. Results display here; the "
           "stored signals update on the next full run.")


@st.cache_data(ttl=900, show_spinner=False)
def _live_news(account: str):
    """Live fetch, cached 15 minutes so reruns and re-clicks stay instant."""
    articles = news.filter_relevant(account, news.fetch_company_news(account))
    return news.score_articles(articles), articles


if selected_account:
    target = selected_account
    run_check = True
    st.markdown(f"Showing live results for **{target}** - selected in the "
                "table above. Deselect the row (click it again or press "
                "Esc) to use the manual picker.")
else:
    target = st.selectbox("Account", df["account"].sort_values(),
                          key="live_check")
    run_check = st.button("Check live now")

if run_check:
    try:
        with st.spinner(f"Fetching Google News for {target}..."):
            score, articles = _live_news(target)
        st.metric("Momentum right now", score,
                  delta=f"+{news.score_to_adjustment(score)} pts if applied")
        if not articles:
            st.caption("No AI-related coverage found in the last "
                       f"{config.NEWS_LOOKBACK_DAYS} days - that is common "
                       "for enterprises outside the tech press cycle.")
        for a in articles[:8]:
            st.markdown(f"- {a['published'].date()} · [{a['title']}]({a['link']})")
    except Exception:
        st.error("Could not reach Google News from this network. This works "
                 "on a normal internet connection and in the scheduled "
                 "GitHub Action.")
