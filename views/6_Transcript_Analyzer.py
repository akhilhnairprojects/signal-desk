"""Transcript Analyzer v2: transformer sentiment, next steps, and a
feedback loop that makes the analyzer smarter over time."""

from pathlib import Path

import plotly.express as px
import streamlit as st

from src import config, enrich, transcript
from src.app_helpers import NEUTRAL, PLOTLY_LAYOUT, get_data, page_header, refresh_data

df, _, _ = get_data()
page_header(
    "Meeting Transcript Analyzer",
    "Paste a Zoom/Teams transcript. The analyzer scores sentence-level "
    "sentiment, surfaces pain points with evidence, recommends positioning "
    "plays, and produces the concrete next steps for the rep. The engine in "
    "use is named below the results.",
)

SAMPLE_PATH = (Path(__file__).resolve().parents[1] / "data" /
               "sample_transcripts" / "discovery_call_sample.txt")


@st.cache_data(show_spinner=False)
def _read_sample() -> str:
    return SAMPLE_PATH.read_text(encoding="utf-8")


@st.cache_data(show_spinner=False)
def _analyze(text: str, account: str | None) -> dict:
    """Cached on (transcript, linked account).

    Sentiment inference runs over every sentence, so without this every
    widget interaction on the page re-ran the whole model.
    """
    frame, _, _ = get_data()
    match = frame[frame["account"] == account] if account else None
    row = match.iloc[0] if match is not None and not match.empty else None
    return transcript.analyze(text, row)

# ------------------------------------------------------------------ Input
src_choice = st.radio(
    "Transcript source", ["Paste text", "Upload .txt file", "Load sample call"],
    horizontal=True)

text = ""
if src_choice == "Paste text":
    text = st.text_area("Transcript text", height=220,
                        placeholder="Paste the meeting transcript here...")
elif src_choice == "Upload .txt file":
    up = st.file_uploader("Upload transcript", type=["txt"])
    if up:
        text = up.read().decode("utf-8", errors="ignore")
else:
    text = _read_sample()
    with st.expander("View the sample transcript"):
        st.text(text)

linked_account = st.selectbox(
    "Link to an account (optional)",
    ["- none -"] + df["account"].sort_values().tolist())

if not text.strip():
    st.stop()

account_row = (df[df["account"] == linked_account].iloc[0]
               if linked_account != "- none -" else None)

# --------------------------------------------------------------- Analysis
with st.spinner("Analysing transcript..."):
    result = _analyze(
        text, None if linked_account == "- none -" else linked_account)
sent = result["sentiment"]

st.caption(f"Engine: {sent['engine']}")

st.divider()
c1, c2, c3 = st.columns(3)
c1.metric("Overall tone", sent["label"])
c2.metric("Sentiment score", f"{sent['overall']:+.2f}",
          help="Average sentence-level sentiment, -1 (negative) to +1 "
               "(positive)")
c3.metric("Sentences analysed", result["sentence_count"])

pos, neg = st.columns(2)
with pos:
    st.markdown("**Strongest positive moment**")
    st.success(sent["best"] or "-")
with neg:
    st.markdown("**Strongest concern raised**")
    st.error(sent["worst"] or "-")

# ---------------------------------------------------------- Next steps
st.subheader("Next possible steps")
st.caption("A concrete engagement plan from what was said, how it was said, "
           "and the account's current position.")
for i, step in enumerate(result["next_steps"], 1):
    st.markdown(f"**{i}.** {step}")

# ------------------------------------------------------------- Pain points
st.subheader("Pain points detected")
if not result["pain_points"]:
    st.caption("No taxonomy matches found in this transcript.")
else:
    pp = result["pain_points"]
    chart_df = {"category": [p["category"] for p in pp],
                "mentions": [p["mentions"] for p in pp]}
    fig = px.bar(chart_df, x="mentions", y="category", orientation="h",
                 color_discrete_sequence=[NEUTRAL], text="mentions")
    fig.update_layout(xaxis_title="Mentions", yaxis_title="",
                      yaxis=dict(autorange="reversed"),
                      height=80 + 42 * len(pp), **PLOTLY_LAYOUT)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Evidence and positioning plays")
    for p in pp:
        with st.expander(f"{p['category']}  ·  {p['mentions']} mentions"):
            for e in p["evidence"]:
                st.markdown(f"> {e}")
            st.markdown(f"**Suggested play:** {p['positioning']}")

with st.expander("Frequent keywords"):
    st.write("  ·  ".join(f"**{w}** ({c})" for w, c in result["keywords"]))

# ------------------------------------------------- Save into the profile
st.divider()
if linked_account != "- none -":
    top3 = ", ".join(p["category"] for p in result["pain_points"][:3]) or "none"
    summary = (f"Call analysed: tone {sent['label']} ({sent['overall']:+.2f}). "
               f"Top pain points: {top3}. "
               f"Next step: {result['next_steps'][0] if result['next_steps'] else '-'}")
    st.markdown(f"**Summary to save:** {summary}")
    impact = ("Positive" if sent["overall"] >= 0.2
              else "Negative" if sent["overall"] <= -0.2 else "Neutral")
    if st.button(f"Save summary to {linked_account}'s profile", type="primary"):
        enrich.append_note(linked_account, "Transcript Analyzer",
                           "Technical Context", impact, summary)
        refresh_data()
        st.success(f"Saved to {linked_account}. See it on the Knowledge "
                   "Base page.")
else:
    st.caption("Link an account above to save this analysis into its profile.")

# ------------------------------------------------------ Adaptive learning
st.divider()
st.subheader("Teach the analyzer")
st.caption("Corrections improve the system: missed phrases become new "
           "taxonomy keywords immediately, and sentiment corrections build "
           "the labelled dataset used to fine-tune the model on your "
           "domain (scripts/train_domain_model.py).")

teach1, teach2 = st.columns(2)

with teach1:
    st.markdown("**The analyzer missed a pain point**")
    with st.form("kw_form", clear_on_submit=True):
        kw_cat = st.selectbox("It belongs to",
                              list(config.PAIN_POINT_TAXONOMY))
        kw_term = st.text_input("The word or phrase it should catch",
                                placeholder="e.g. opex, dark fiber")
        kw_by = st.text_input("Your name (optional)")
        kw_saved = st.form_submit_button("Add keyword")
    if kw_saved and kw_term.strip():
        transcript.learn_keyword(kw_cat, kw_term, kw_by)
        st.success(f"Learned. '{kw_term.strip()}' now counts toward "
                   f"{kw_cat} in every future analysis.")

with teach2:
    st.markdown("**The tone reading was off**")
    with st.form("fb_form", clear_on_submit=True):
        fb_correct = st.selectbox(
            "The call was actually...",
            ["Positive", "Mixed / Neutral", "Negative"])
        fb_saved = st.form_submit_button("Record correction")
    if fb_saved:
        transcript.record_feedback(
            linked_account if linked_account != "- none -" else "",
            sent["label"], fb_correct, text[:500])
        st.success("Recorded. Corrections accumulate into the fine-tuning "
                   "dataset for the domain model.")
