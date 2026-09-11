"""Segments: two clusterings, two projections, one interactive map."""

import plotly.express as px
import streamlit as st

from src import config, segment
from src.app_helpers import (PLOTLY_LAYOUT, SEGMENT_COLORS, get_data,
                             highlighted_segment, page_header,
                             segment_highlight_selector,
                             segment_row_styler, set_segment_highlight)

df, _, meta = get_data()
page_header(
    "Account Segments",
    "Clustering on the five standardised demand signals. Segments group "
    "accounts by behaviour, not industry - which is what makes "
    "cross-industry positioning plays possible.",
)

if meta.get("segmentation_source") == "published":
    st.caption("Segments and both projections come from the published "
               "snapshot, keyed to a fingerprint of the current signal "
               "matrix. Change a signal, a weight, or the account universe "
               "and they are recomputed on the spot. It also means the map "
               "stays put between visits instead of shifting every time the "
               "app restarts.")
else:
    st.caption("Segments were computed live for this universe - the "
               "published snapshot does not match the current signals.")

seg_order = (df.groupby("segment")["base_score"].mean()
               .sort_values(ascending=False).index.tolist())
seg_colors = {s: SEGMENT_COLORS[i % len(SEGMENT_COLORS)]
              for i, s in enumerate(seg_order)}

sel_col, _ = st.columns([1, 2])
with sel_col:
    segment_highlight_selector(seg_order)
hl = highlighted_segment()
if hl:
    st.caption(f"'{hl}' is highlighted everywhere - this page, the "
               "Account Explorer and the Overview all emphasise it until "
               "you pick another segment or '(none)'. Clicking a point of "
               "the highlighted segment on the map also clears it.")

# -------------------------------------------------------- Segment profiles
st.subheader("Segment profiles")
profiles = segment.segment_profiles(df)
display = profiles.rename(columns={
    "segment": "Segment", "accounts": "Accounts", "avg_score": "Avg score",
    "top_industries": "Top industries",
    **{f"avg_{k}": config.SIGNAL_LABELS[k] for k in config.SIGNAL_WEIGHTS},
})
st.dataframe(segment_row_styler(display, hl, column="Segment")
             if hl else display,
             width="stretch", hide_index=True)

# -------------------------------------------------- Signal shape by segment
st.subheader("What makes each segment different")
long = df.melt(id_vars="segment", value_vars=list(config.SIGNAL_WEIGHTS),
               var_name="signal", value_name="value")
long["signal"] = long["signal"].map(config.SIGNAL_LABELS)
avg = long.groupby(["segment", "signal"], as_index=False)["value"].mean()
fig = px.bar(avg, x="signal", y="value", color="segment", barmode="group",
             category_orders={"segment": seg_order},
             color_discrete_map=seg_colors)
fig.update_layout(xaxis_title="", yaxis_title="Average signal score",
                  legend_title="Segment", legend_itemclick=False,
                  legend_itemdoubleclick=False, **PLOTLY_LAYOUT)
if hl:
    for trace in fig.data:
        trace.marker.opacity = 0.95 if trace.name == hl else 0.25
st.plotly_chart(fig, width="stretch")

st.info("How to use this: pick one strong reference customer per segment, "
        "build the positioning story around that segment's dominant signals, "
        "then work the rest of the segment with the same story. Use the "
        "HDBSCAN view to spot accounts that need a bespoke approach.")

st.divider()
st.subheader("Segment map")

# ------------------------------------------------------------- Controls
c1, c2 = st.columns(2)
with c1:
    projection = st.radio(
        "Projection", ["PCA", "UMAP"], horizontal=True,
        help="PCA is linear and preserves the global picture "
             f"({sum(meta['explained_variance']):.0%} of variance shown). "
             "UMAP is non-linear and separates overlapping clusters more "
             "cleanly - use it when PCA points pile on top of each other.")
with c2:
    view_mode = st.radio(
        "Clustering view", ["Segments (K-Means)", "Density (HDBSCAN)"],
        horizontal=True,
        help="K-Means assigns every account to a named segment. HDBSCAN is "
             "density-based: it handles overlapping groups honestly and "
             "labels genuinely unusual accounts as outliers instead of "
             "forcing them into a cluster.")

if projection == "UMAP" and not meta.get("umap_available", False):
    st.warning("UMAP is not installed in this environment - showing PCA "
               "coordinates instead.")
x_col, y_col = (("umap_x", "umap_y") if projection == "UMAP"
                else ("pca_x", "pca_y"))

# ------------------------------------------------------------ Cluster map
if view_mode.startswith("Segments"):
    color_col, color_map, orders = "segment", seg_colors, {"segment": seg_order}
    st.caption(f"K-Means selected k = {meta['k']} by silhouette score "
               f"({meta['silhouette']}).")
else:
    dens_order = sorted(df["density_cluster"].unique(),
                        key=lambda v: (v == "Outlier", v))
    color_map = {d: ("#B23B3B" if d == "Outlier"
                     else SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
                 for i, d in enumerate(dens_order)}
    color_col, orders = "density_cluster", {"density_cluster": dens_order}
    st.caption(f"HDBSCAN found {meta['hdbscan_clusters']} density groups and "
               f"{meta['hdbscan_outliers']} outliers (accounts whose signal "
               "profile does not fit any dense group).")

fig = px.scatter(
    df, x=x_col, y=y_col, color=color_col,
    category_orders=orders, color_discrete_map=color_map,
    hover_name="account",
    hover_data={"industry": True, "adjusted_score": ":.0f", "tier": True,
                "segment": True, x_col: False, y_col: False},
    size="adjusted_score", size_max=14, opacity=0.85,
)
fig.update_layout(
    xaxis_title="", yaxis_title="",
    xaxis=dict(showticklabels=False), yaxis=dict(showticklabels=False),
    legend_title=view_mode.split(" ")[0], height=520,
    legend_itemclick=False, legend_itemdoubleclick=False, **PLOTLY_LAYOUT,
)
if hl and view_mode.startswith("Segments"):
    for trace in fig.data:
        trace.marker.opacity = 0.95 if trace.name == hl else 0.12

map_event = st.plotly_chart(fig, width="stretch", key="segment_map",
                            on_select="rerun")

# A click on a point selects its segment as the global highlight
# (clicking the highlighted segment again clears it - standard selection).
try:
    map_points = map_event.selection.points
except Exception:
    map_points = []
if map_points and view_mode.startswith("Segments"):
    curve = map_points[0].get("curve_number")
    clicked = fig.data[curve].name if curve is not None else None
    if clicked in seg_order:
        set_segment_highlight(clicked)
        st.session_state.pop("segment_map", None)
        st.rerun()

st.caption("The chart is fully interactive: drag to zoom into overlapping "
           "points, double-click to reset - and click any point to "
           "highlight its whole segment across the app (click the "
           "highlighted segment again to clear).")

# --------------------------------------------------------------- Outliers
if view_mode.startswith("Density") and meta["hdbscan_outliers"]:
    with st.expander(f"Outlier accounts ({meta['hdbscan_outliers']})"):
        st.caption("Unusual signal profiles - often the most interesting "
                   "conversations, since no standard playbook fits them.")
        st.dataframe(
            df[df["density_cluster"] == "Outlier"]
            [["account", "industry", *config.SIGNAL_WEIGHTS,
              "adjusted_score", "tier"]],
            width="stretch", hide_index=True)

