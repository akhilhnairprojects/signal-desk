"""App entry point: identity, favicon, and navigation.

The sidebar page names live here (st.navigation supersedes the automatic
pages/ listing). The app's display name is config.APP_NAME - one constant,
used for both the landing entry and the browser tab.
"""

import streamlit as st

from src import config
from src.app_helpers import apply_branding

st.set_page_config(
    page_title=config.APP_NAME,
    page_icon=(str(config.FAVICON_PATH)
               if config.FAVICON_PATH.exists()
               else ":material/bar_chart:"),
    layout="wide",
)

pg = st.navigation([
    st.Page("pages/0_Overview.py", title="Overview",
            icon=":material/dashboard:", default=True),
    st.Page("pages/1_Account_Explorer.py", title="Account Explorer",
            icon=":material/search:"),
    st.Page("pages/2_Segments.py", title="Segments",
            icon=":material/scatter_plot:"),
    st.Page("pages/3_News_Monitor.py", title="News Monitor",
            icon=":material/newspaper:"),
    st.Page("pages/4_Knowledge_Base.py", title="Knowledge Base",
            icon=":material/description:"),
    st.Page("pages/5_Add_Company.py", title="Add a Company",
            icon=":material/add_business:"),
    st.Page("pages/6_Transcript_Analyzer.py", title="Transcript Analyzer",
            icon=":material/graphic_eq:"),
    st.Page("pages/7_Competitive_Intel.py", title="Competitive Intel",
            icon=":material/flag:"),
])

# Before pg.run(), so the chrome is styled while the pipeline spinner runs
# rather than snapping into place once the data lands.
apply_branding()
pg.run()
