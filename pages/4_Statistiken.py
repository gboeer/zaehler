import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import plotly.express as px
import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, Price, Reading
from zaehler.utils.calculations import compute_consumption, compute_costs, resample_consumption

st.set_page_config(page_title="Statistiken", page_icon="📊", layout="wide")
st.title("Statistiken & Auswertungen")

session = get_session()

meters = session.query(Meter).order_by(Meter.name).all()

if not meters:
    st.warning("Keine Zähler vorhanden.")
    st.stop()

meter_options = {f"{m.name} ({m.meter_type.value})": m for m in meters}
selected_label = st.selectbox("Zähler auswählen", list(meter_options.keys()))
meter = meter_options[selected_label]

readings = (
    session.query(Reading)
    .filter(Reading.meter_id == meter.id)
    .order_by(Reading.reading_date)
    .all()
)

if len(readings) < 2:
    st.info("Mindestens 2 Ablesungen benötigt für Statistiken.")
    session.close()
    st.stop()

df = pd.DataFrame([{"reading_date": r.reading_date, "value": r.value} for r in readings])
df = compute_consumption(df)
df_valid = df.dropna(subset=["consumption"])

# Zeitraum-Filter
st.sidebar.header("Zeitraum")
min_date = df["reading_date"].min()
max_date = df["reading_date"].max()
date_from = st.sidebar.date_input("Von", value=min_date, min_value=min_date, max_value=max_date)
date_to = st.sidebar.date_input("Bis", value=max_date, min_value=min_date, max_value=max_date)

df_filtered = df_valid[
    (df_valid["reading_date"] >= date_from) & (df_valid["reading_date"] <= date_to)
]

# Aggregation
agg_label = st.sidebar.selectbox("Aggregation", ["Rohdaten", "Monatlich", "Quartal", "Jährlich"])
freq_map = {"Monatlich": "ME", "Quartal": "QE", "Jährlich": "YE"}

# --- Kennzahlen ---
st.subheader("Kennzahlen")
col1, col2, col3, col4 = st.columns(4)
total = df_filtered["consumption"].sum()
avg_daily = df_filtered["daily_avg"].mean()
max_period = df_filtered["consumption"].max()
min_period = df_filtered["consumption"].min()

col1.metric("Gesamtverbrauch", f"{total:,.2f} {meter.unit}")
col2.metric("Ø Täglich", f"{avg_daily:.2f} {meter.unit}/Tag" if avg_daily else "—")
col3.metric("Max. Periode", f"{max_period:,.2f} {meter.unit}")
col4.metric("Min. Periode", f"{min_period:,.2f} {meter.unit}")

# --- Kosten ---
prices = session.query(Price).filter(Price.meter_id == meter.id).all()
if prices:
    prices_df = pd.DataFrame(
        [{"valid_from": p.valid_from, "price_per_unit": p.price_per_unit, "base_price_per_month": p.base_price_per_month}
         for p in prices]
    )
    total_days = int(df_filtered["days"].sum()) if "days" in df_filtered.columns else None
    cost_info = compute_costs(total, date_to, prices_df, days=total_days)
    if cost_info["total_cost"] is not None:
        st.subheader("Kosten (Schätzung)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Arbeitspreis", f"{cost_info['consumption_cost']:,.2f} €")
        c2.metric("Grundgebühr (Periode)", f"{cost_info['base_price']:,.2f} €")
        c3.metric("Gesamt", f"{cost_info['total_cost']:,.2f} €")

st.divider()

# --- Verbrauchsdiagramm ---
st.subheader("Verbrauchsverlauf")

if agg_label == "Rohdaten":
    plot_df = df_filtered[["reading_date", "consumption"]].copy()
    plot_df.columns = ["period", "consumption"]
else:
    plot_df = resample_consumption(df_filtered, freq=freq_map[agg_label])

if not plot_df.empty:
    fig = px.bar(
        plot_df,
        x="period",
        y="consumption",
        labels={"period": "Datum", "consumption": f"Verbrauch ({meter.unit})"},
        color_discrete_sequence=["#1f77b4"],
    )
    fig.update_layout(margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

# --- Zählerstandsverlauf ---
st.subheader("Zählerstandsverlauf")
df_vals = df[["reading_date", "value"]].copy()
df_vals = df_vals[(df_vals["reading_date"] >= date_from) & (df_vals["reading_date"] <= date_to)]
fig2 = px.line(
    df_vals,
    x="reading_date",
    y="value",
    markers=True,
    labels={"reading_date": "Datum", "value": f"Stand ({meter.unit})"},
)
fig2.update_layout(margin=dict(t=20, b=20))
st.plotly_chart(fig2, use_container_width=True)

# --- Rohdaten-Tabelle ---
with st.expander("Rohdaten anzeigen"):
    display_df = df_filtered[["reading_date", "value", "prev_value", "consumption", "days", "daily_avg"]].copy()
    display_df.columns = ["Datum", f"Stand ({meter.unit})", f"Vorstand ({meter.unit})", f"Verbrauch ({meter.unit})", "Tage", f"Ø/Tag ({meter.unit})"]
    display_df["Datum"] = display_df["Datum"].apply(lambda d: d.strftime("%d.%m.%Y"))
    st.dataframe(display_df, use_container_width=True, hide_index=True)

session.close()
