import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import plotly.express as px
import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, Reading
from zaehler.utils.calculations import compute_consumption

st.set_page_config(
    page_title="Zählerverwaltung",
    page_icon="⚡",
    layout="wide",
)

st.title("Zählerverwaltung")
st.markdown("Übersicht über alle Zähler und letzten Ablesungen.")

session = get_session()

all_meters = session.query(Meter).filter(Meter.active == 1).all()

if not all_meters:
    st.info("Noch keine Zähler angelegt. Lege zuerst einen Zähler unter **Zähler verwalten** an.")
    st.stop()

TYPE_ICONS = {"Strom": "⚡", "Gas": "🔥", "Wasser": "💧"}

hauptzaehler = [m for m in all_meters if m.parent_id is None]


def render_meter_card(meter: Meter, indent: bool = False):
    icon = TYPE_ICONS.get(meter.meter_type.value, "📊")
    readings = (
        session.query(Reading)
        .filter(Reading.meter_id == meter.id)
        .order_by(Reading.reading_date.desc())
        .limit(2)
        .all()
    )

    prefix = "↳ " if indent else ""
    with st.container(border=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.subheader(f"{prefix}{icon} {meter.name}")
            if meter.meter_number:
                st.caption(f"Zählernummer: {meter.meter_number}")
            if meter.location:
                st.caption(f"Standort: {meter.location}")
            if indent:
                st.caption("Unterzähler")

        if readings:
            latest = readings[0]
            with col2:
                st.metric(
                    label="Letzter Stand",
                    value=f"{latest.value:,.2f} {meter.unit}",
                )
                st.caption(f"vom {latest.reading_date.strftime('%d.%m.%Y')}")

            if len(readings) == 2:
                prev = readings[1]
                diff = latest.value - prev.value
                with col3:
                    st.metric(
                        label="Verbrauch (letzte Periode)",
                        value=f"{diff:,.2f} {meter.unit}",
                    )
        else:
            with col2:
                st.info("Noch keine Ablesungen.")


# Zähler als Baum anzeigen: Hauptzähler + eingerückte Unterzähler
for hm in hauptzaehler:
    render_meter_card(hm, indent=False)
    unterzaehler = [m for m in all_meters if m.parent_id == hm.id]
    if unterzaehler:
        cols = st.columns(len(unterzaehler))
        for col, um in zip(cols, unterzaehler):
            with col:
                icon = TYPE_ICONS.get(um.meter_type.value, "📊")
                readings = (
                    session.query(Reading)
                    .filter(Reading.meter_id == um.id)
                    .order_by(Reading.reading_date.desc())
                    .limit(2)
                    .all()
                )
                with st.container(border=True):
                    st.markdown(f"↳ {icon} **{um.name}**")
                    if um.meter_number:
                        st.caption(f"Nr: {um.meter_number}")
                    if readings:
                        latest = readings[0]
                        st.metric(
                            "Letzter Stand",
                            f"{latest.value:,.2f} {um.unit}",
                        )
                        st.caption(f"vom {latest.reading_date.strftime('%d.%m.%Y')}")
                        if len(readings) == 2:
                            diff = readings[0].value - readings[1].value
                            st.metric("Letzte Periode", f"{diff:,.2f} {um.unit}")
                    else:
                        st.info("Keine Ablesungen")

st.divider()

# Verbrauchsübersicht letzte 12 Monate (nur Hauptzähler)
st.subheader("Verbrauchsübersicht (letzte 12 Monate)")

for meter in all_meters:
    readings = (
        session.query(Reading)
        .filter(Reading.meter_id == meter.id)
        .order_by(Reading.reading_date)
        .all()
    )
    if len(readings) < 2:
        continue

    df = pd.DataFrame(
        [{"reading_date": r.reading_date, "value": r.value} for r in readings]
    )
    df = compute_consumption(df)
    df = df.dropna(subset=["consumption"])
    df["reading_date"] = pd.to_datetime(df["reading_date"])

    cutoff = pd.Timestamp.now() - pd.DateOffset(months=12)
    df = df[df["reading_date"] >= cutoff]

    if df.empty:
        continue

    icon = TYPE_ICONS.get(meter.meter_type.value, "📊")
    is_child = meter.parent_id is not None
    title = f"{'↳ ' if is_child else ''}{icon} {meter.name}"
    fig = px.bar(
        df,
        x="reading_date",
        y="consumption",
        title=title,
        labels={"reading_date": "Datum", "consumption": f"Verbrauch ({meter.unit})"},
    )
    fig.update_layout(showlegend=False, margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

session.close()
