"""App entry point: identity, favicon, and navigation.

The page files live in views/, not pages/, and the name matters. Streamlit
auto-discovers any directory literally called pages/ and serves those files
as routes of their own - which bypasses this file entirely, so a deep link
would render with no set_page_config, no navigation and no styling. Naming
the directory views/ makes st.navigation below the only router.

The app's display name is config.APP_NAME - one constant, used for both the
sidebar wordmark and the browser tab.
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
    st.Page("views/0_Overview.py", title="Overview",
            icon=":material/dashboard:", default=True),
    st.Page("views/1_Account_Explorer.py", title="Account Explorer",
            icon=":material/search:"),
    st.Page("views/2_Segments.py", title="Segments",
            icon=":material/scatter_plot:"),
    st.Page("views/3_News_Monitor.py", title="News Monitor",
            icon=":material/newspaper:"),
    st.Page("views/4_Knowledge_Base.py", title="Knowledge Base",
            icon=":material/description:"),
    st.Page("views/5_Add_Company.py", title="Add a Company",
            icon=":material/add_business:"),
    st.Page("views/6_Transcript_Analyzer.py", title="Transcript Analyzer",
            icon=":material/graphic_eq:"),
    st.Page("views/7_Competitive_Intel.py", title="Competitive Intel",
            icon=":material/flag:"),
])

# Before pg.run(), so the chrome is styled while the pipeline spinner runs
# rather than snapping into place once the data lands.
apply_branding()
pg.run()
