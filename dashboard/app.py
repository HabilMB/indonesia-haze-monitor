"""Indonesia Haze Monitor: modeled PM2.5 around fire-prone cities next to the satellite fire hotspots near them."""
import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

import loaders
from shape import RING_INNER, RING_OUTER, latest_snapshot, ring_breakdown, season_ranking

# Reference palette (dataviz skill): two categorical slots, recessive chrome, ink for text.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRID = "#e1e0d9"
MUTED = "#898781"
INK = "#0b0b0b"
RANGES = {"Last 30 days": 30, "Last 60 days": 60, "Whole season": None}

st.set_page_config(page_title="Indonesia Haze Monitor", page_icon="🔥", layout="wide")


def style(chart: alt.Chart) -> alt.Chart:
    return chart.configure_axis(
        gridColor=GRID, domainColor="#c3c2b7", labelColor=MUTED, titleColor=MUTED, tickColor=GRID
    ).configure_axisY(minExtent=64).configure_view(strokeWidth=0).configure_legend(labelColor=INK, titleColor=MUTED, orient="top")


try:
    city_day = loaders.load_city_day()
    cities = loaders.load_cities()
    hotspots = loaders.load_recent_hotspots()
except loaders.MissingConfig as e:
    st.error(str(e))
    st.stop()

latest, snapshot = latest_snapshot(city_day)

st.title("Indonesia Haze Monitor")
st.markdown(
    "Satellite fire hotspots (cause) next to modeled PM2.5 (effect) around fire-prone Indonesian cities, "
    "during the 2026 fire season."
)
st.caption(f"Data through {latest:%Y-%m-%d} (UTC) · refreshed daily at 06:00 UTC")

# Worst city right now
worst = snapshot.iloc[0]
st.subheader(f"Worst air right now: {worst.city_name}")
tile, others = st.columns([1, 2])
with tile:
    st.metric(f"Daily mean PM2.5, {latest:%d %b} (UTC)", f"{worst.pm2_5_mean:,.0f} µg/m³")
    st.metric("Fire hotspots within 100 km that day", f"{worst.hotspots_100km:,}")
with others:
    st.dataframe(
        snapshot.iloc[1:][["city_name", "pm2_5_mean", "hotspots_100km"]],
        column_config={
            "city_name": "Other cities",
            "pm2_5_mean": st.column_config.NumberColumn("PM2.5 (µg/m³)", format="%.0f"),
            "hotspots_100km": st.column_config.NumberColumn("Hotspots ≤100 km", format="%d"),
        },
        hide_index=True,
        use_container_width=True,
    )

# Filters, one row above the charts
st.divider()
names = list(cities["city_name"])
pick, span = st.columns([1, 2])
with pick:
    city = st.selectbox("City", names, index=names.index(worst.city_name))
with span:
    window = st.radio("Period", list(RANGES), horizontal=True)
days = RANGES[window]
start = latest - pd.Timedelta(days=days - 1) if days else city_day["date_utc"].min()
selected = city_day[(city_day["city_name"] == city) & (city_day["date_utc"] >= start)]
# Dates reach Vega without a timezone and are parsed as browser-local, so the domain and
# the time unit stay local too; the calendar days (UTC in the data) then can't shift.
day_domain = [f"{start:%Y-%m-%d}T00:00:00", f"{latest + pd.Timedelta(days=1):%Y-%m-%d}T00:00:00"]
date_axis = alt.Axis(format="%d %b", labelAngle=0, tickCount=8)
x = alt.X("yearmonthdate(date_utc):T", title=None, bandPosition=0.5, scale=alt.Scale(domain=day_domain, padding=0), axis=date_axis)

# PM2.5 and hotspots as two charts on one shared x domain (never a dual axis)
hover = alt.selection_point(fields=["date_utc"], nearest=True, on="pointerover", empty=False)
base = alt.Chart(selected).encode(x=x)
pm_line = base.mark_line(strokeWidth=2, color=BLUE).encode(y=alt.Y("pm2_5_mean:Q", title="µg/m³"))
pm_points = base.mark_point(size=80, filled=True, color=BLUE).encode(
    y="pm2_5_mean:Q",
    opacity=alt.condition(hover, alt.value(1), alt.value(0)),
    tooltip=[
        alt.Tooltip("date_utc:T", title="Date (UTC)"),
        alt.Tooltip("pm2_5_mean:Q", title="Daily mean PM2.5", format=",.0f"),
        alt.Tooltip("pm2_5_max:Q", title="Hourly peak", format=",.0f"),
    ],
).add_params(hover)
pm_rule = base.mark_rule(color=MUTED).encode(opacity=alt.condition(hover, alt.value(0.6), alt.value(0)))
st.markdown(f"**Daily mean PM2.5 (µg/m³), {city}**")
st.altair_chart(style((pm_line + pm_rule + pm_points).properties(height=260)), use_container_width=True)

rings = ring_breakdown(selected).assign(order=lambda d: (d["ring"] == RING_OUTER).astype(int))
bars = alt.Chart(rings).mark_bar(width=alt.RelativeBandSize(0.75), cornerRadius=2, stroke="#fcfcfb", strokeWidth=1).encode(
    x=x,
    y=alt.Y("sum(hotspots):Q", title="hotspots"),
    color=alt.Color("ring:N", title=None, scale=alt.Scale(domain=[RING_INNER, RING_OUTER], range=[BLUE, ORANGE])),
    order=alt.Order("order:Q"),
    tooltip=[
        alt.Tooltip("date_utc:T", title="Date (UTC)"),
        alt.Tooltip("ring:N", title="Distance"),
        alt.Tooltip("hotspots:Q", title="Hotspots", format=","),
    ],
)
st.markdown(f"**Nearby fire hotspots per day, {city}**")
st.altair_chart(style(bars.properties(height=230)), use_container_width=True)

with st.expander("Show data table"):
    st.dataframe(
        selected[["date_utc", "pm2_5_mean", "pm2_5_max", "us_aqi_max", "hotspots_100km", "hotspots_250km"]],
        column_config={
            "date_utc": st.column_config.DateColumn("Date (UTC)"),
            "pm2_5_mean": st.column_config.NumberColumn("PM2.5 mean", format="%.1f"),
            "pm2_5_max": st.column_config.NumberColumn("PM2.5 hourly peak", format="%.1f"),
            "us_aqi_max": "US AQI peak",
            "hotspots_100km": "Hotspots ≤100 km",
            "hotspots_250km": "Hotspots ≤250 km",
        },
        hide_index=True,
        use_container_width=True,
    )

# Map of the latest hotspots
st.divider()
st.subheader("Fire hotspots, last 3 days")
city_row = cities[cities["city_name"] == city]
layers = [
    pdk.Layer(
        "ScatterplotLayer", city_row, get_position="[longitude, latitude]", get_radius=radius,
        filled=False, stroked=True, get_line_color=[82, 81, 78, 220], line_width_min_pixels=1.5,
    )
    for radius in (100_000, 250_000)
]
if hotspots.empty:
    st.caption("No nominal/high-confidence hotspots in the last 3 days.")
else:
    layers.insert(0, pdk.Layer(
        "ScatterplotLayer", hotspots.assign(acq_date=hotspots["acq_date"].astype(str)),
        get_position="[longitude, latitude]", get_radius=2500, radius_min_pixels=1.5,
        get_fill_color=[235, 104, 52, 150], pickable=True,
    ))
layers += [
    pdk.Layer("ScatterplotLayer", cities, get_position="[longitude, latitude]", get_radius=6000,
              radius_min_pixels=4, get_fill_color=[11, 11, 11, 230]),
    pdk.Layer("TextLayer", cities, get_position="[longitude, latitude]", get_text="city_name", get_size=12,
              get_color=[11, 11, 11, 255], get_pixel_offset=[8, 0], get_text_anchor='"start"',
              get_alignment_baseline='"center"'),
]
st.pydeck_chart(pdk.Deck(
    layers=layers,
    initial_view_state=pdk.ViewState(latitude=-2.5, longitude=117.0, zoom=3.6),
    map_style=pdk.map_styles.CARTO_LIGHT,
    tooltip={"text": "Hotspot {acq_date}\nFire radiative power {frp} MW"},
))
st.caption(f"Rings show 100 and 250 km around {city}. Orange dots: VIIRS detections, nominal and high confidence.")

# Season ranking
st.divider()
st.subheader("Season so far: mean PM2.5 by city")
ranking = season_ranking(city_day)
rank_chart = alt.Chart(ranking).mark_bar(color=BLUE, cornerRadiusEnd=4, height=18).encode(
    x=alt.X("pm2_5_mean:Q", title="mean of daily PM2.5 (µg/m³)", axis=alt.Axis(tickCount=6)),
    y=alt.Y("city_name:N", title=None, sort="-x"),
    tooltip=[
        alt.Tooltip("city_name:N", title="City"),
        alt.Tooltip("pm2_5_mean:Q", title="Mean PM2.5", format=",.0f"),
        alt.Tooltip("hotspots_250km:Q", title="Hotspots ≤250 km (season)", format=","),
    ],
)
st.altair_chart(style(rank_chart.properties(height=40 * len(ranking))), use_container_width=True)
st.caption(f"{city_day['date_utc'].min():%d %b} – {latest:%d %b %Y} (UTC).")

# Caveats and attribution
st.divider()
st.caption("PM2.5 is modeled (CAMS via Open-Meteo), not measured by ground sensors.")
st.caption("Hotspots are satellite thermal detections (NASA FIRMS VIIRS, nominal and high confidence), not confirmed fires.")
st.caption("Days are UTC. Nearby hotspots do not prove the smoke came from them: wind moves haze.")
st.caption("Data: NASA FIRMS, Open-Meteo (CC BY 4.0) / CAMS.")
