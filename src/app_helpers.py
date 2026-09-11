"""Shared helpers: cached data loading, visual identity, and chart defaults.

The palette is deliberately lopsided. Everything structural is a cool slate
neutral; amber is the only saturated colour in the system and it is spent
exclusively on Tier 1 - the accounts the model says to engage now. That is
what makes the eye land on the answer instead of wandering a grid of equally
bright cards.
"""

import streamlit as st

from src import build_dataset, config, store

# Amber is the emphasis colour and is spent only on what the model is
# pointing at: Tier 1, the selected account, a final total. Anything with
# no particular thing to say uses NEUTRAL, so amber never becomes wallpaper.
PRIMARY = "#F0A63C"
NEUTRAL = "#4EA8DE"
TIER_COLORS = {"Tier 1": "#F0A63C", "Tier 2": "#7C8FA8", "Tier 3": "#4A5668"}
# Segments are ordered by average score, so amber-first is meaningful here.
SEGMENT_COLORS = ["#F0A63C", "#4EA8DE", "#66C2A5", "#C77DBB",
                  "#E8705F", "#9BA7B8"]
# Default categorical cycle for charts that do not set their own colours.
CHART_COLORS = ["#4EA8DE", "#66C2A5", "#C77DBB", "#E8705F", "#9BA7B8",
                "#F0A63C"]

_FONT_STACK = "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
_MONO_STACK = "IBM Plex Mono, SFMono-Regular, Consolas, monospace"

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=_FONT_STACK, size=13, color="#E8EEF6"),
    margin=dict(l=10, r=10, t=40, b=10),
    colorway=CHART_COLORS,
    hoverlabel=dict(font=dict(family=_FONT_STACK, size=12),
                    bgcolor="#131A26", bordercolor="#2C3A54"),
)

_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"], .stApp, button, input, textarea, select {
    font-family: """ + _FONT_STACK + """;}

h1 {font-size: 2.1rem !important; font-weight: 600 !important;
    letter-spacing: -0.025em;}
h2 {font-size: 1.5rem !important; font-weight: 600 !important;
    letter-spacing: -0.015em;}
h3 {font-size: 1.15rem !important; font-weight: 600 !important;}
h4 {font-size: 1rem !important; font-weight: 600 !important;}

.stApp {background: #0B0F17;}
[data-testid="stSidebar"] {background: #0D1420;
    border-right: 1px solid #1C2740;}
[data-testid="stExpander"] {border: 1px solid #22304A; background: #10161F;
    border-radius: 8px;}
hr {border-color: #22304A;}

/* Metrics: quiet slate frames, monospaced figures so columns align. */
[data-testid="stMetric"] {background: #111823; border: 1px solid #22304A;
    border-radius: 8px; padding: 14px 16px;}
[data-testid="stMetricLabel"] p {font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.07em; color: #7C8FA8; font-weight: 500;
    line-height: 1.3;}
/* Tracked uppercase labels overflow narrow columns; wrap them instead of
   letting Streamlit ellipsize "Adjusted score" down to "ADJUST...". */
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] > div {
    white-space: normal; overflow: visible; max-width: 100%;}
[data-testid="stMetricValue"] {font-family: """ + _MONO_STACK + """;
    font-weight: 500; letter-spacing: -0.02em;
    /* Some metrics carry text values ("Watch List", "Tier 3"); let them
       wrap and shrink rather than clipping to "Wa...". */
    white-space: normal; overflow-wrap: anywhere; line-height: 1.15;
    font-size: clamp(1.3rem, 2.2vw, 2.1rem);}

/* The single loud element on the page: the callable list. */
.st-key-hero-metric [data-testid="stMetric"] {border-color: #F0A63C;
    background: linear-gradient(180deg, #201906 0%, #111823 70%);}
.st-key-hero-metric [data-testid="stMetricLabel"] p {color: #F0A63C;}
.st-key-hero-metric [data-testid="stMetricValue"] {color: #F7C67E;}

/* Numerals in tables read as data, not prose. */
[data-testid="stDataFrame"] {font-family: """ + _MONO_STACK + """;
    font-size: 0.82rem;}

.wordmark {font-family: """ + _FONT_STACK + """; font-weight: 600;
    font-size: 0.95rem; letter-spacing: -0.01em; color: #E8EEF6;
    padding: 0.2rem 0 0.1rem 0;}
.wordmark span {color: #F0A63C;}
.wordmark-sub {font-family: """ + _MONO_STACK + """; font-size: 0.63rem;
    text-transform: uppercase; letter-spacing: 0.14em; color: #5A6B80;
    padding-bottom: 0.7rem;}
</style>"""


def apply_branding():
    """Inject the design system and the sidebar wordmark. Runs on every page
    via page_header()."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.sidebar.markdown(
        f'<div class="wordmark">{config.APP_NAME}<span>.</span></div>'
        '<div class="wordmark-sub">demand signal · 160 accounts</div>',
        unsafe_allow_html=True)

    for failure in store.pop_write_failures():
        st.warning(f"Saved locally, but the database rejected the write - "
                   f"{failure}", icon=":material/cloud_off:")


# ---------------------------------------------------------------------------
# Global segment highlighting (persists across pages within a session)
# ---------------------------------------------------------------------------
SEGMENT_HIGHLIGHT_KEY = "segment_highlight"
_HL_CSS = "background-color: rgba(240, 166, 60, 0.22)"


def highlighted_segment():
    """The globally highlighted segment, or None."""
    value = st.session_state.get(SEGMENT_HIGHLIGHT_KEY, "(none)")
    return None if value in (None, "", "(none)") else value


def set_segment_highlight(segment: str) -> None:
    """Standard selection semantics: selecting the already-highlighted
    segment clears it; anything else switches to it."""
    current = st.session_state.get(SEGMENT_HIGHLIGHT_KEY)
    st.session_state[SEGMENT_HIGHLIGHT_KEY] = (
        "(none)" if segment == current else segment)


def segment_highlight_selector(segments, widget=None) -> None:
    """A selectbox bound to the shared highlight state. Render it on any
    page; they all read and write the same session value."""
    widget = widget or st
    options = ["(none)"] + list(segments)
    if st.session_state.get(SEGMENT_HIGHLIGHT_KEY) not in options:
        st.session_state[SEGMENT_HIGHLIGHT_KEY] = "(none)"
    widget.selectbox(
        "Highlight segment", options, key=SEGMENT_HIGHLIGHT_KEY,
        help="Highlights this segment consistently across the app: the "
             "segment map, the profile tables, the Account Explorer and "
             "the Overview. Clicking a point on the segment map sets this "
             "too; picking '(none)' clears it.")


def segment_row_styler(frame, segment, column: str = "segment"):
    """Pandas Styler that shades rows belonging to the highlighted
    segment."""
    def _row(row):
        on = str(row.get(column, "")) == segment
        return [_HL_CSS if on else "" for _ in row]
    return frame.style.apply(_row, axis=1)


@st.cache_data(show_spinner="Building account intelligence...")
def get_data():
    """Run the pipeline once per session / data change."""
    df, notes, meta = build_dataset()
    return df, notes, meta


def refresh_data():
    """Clear every data cache so the next load picks up new notes or data.

    Global rather than per-function: the page modules hold their own caches
    (live news lookups, competitor headlines) that this module cannot import
    without a circular dependency, and a partial clear is what made stale
    rows reappear after an edit.
    """
    st.cache_data.clear()


def page_header(title: str, subtitle: str = ""):
    st.title(title)
    if subtitle:
        st.caption(subtitle)


@st.cache_data(show_spinner=False)
def get_news():
    """Cached news signals and headlines for the app pages."""
    from src import news
    return news.load_signals(), news.load_headlines()


@st.cache_data(show_spinner=False)
def get_kb():
    """Cached knowledge-base articles."""
    from src import enrich
    return enrich.load_kb()
