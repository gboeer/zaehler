import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import date

import pandas as pd
import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, Reading
from zaehler.utils.calculations import compute_consumption

st.set_page_config(page_title="Zählerstände", page_icon="📝", layout="wide")
st.title("Zählerstände")

session = get_session()

meters = session.query(Meter).filter(Meter.active == 1).order_by(Meter.name).all()

if not meters:
    st.warning("Keine aktiven Zähler vorhanden. Bitte zuerst einen Zähler anlegen.")
    st.stop()

meter_options = {f"{m.name} ({m.meter_type.value})": m for m in meters}
selected_label = st.selectbox("Zähler auswählen", list(meter_options.keys()))
meter = meter_options[selected_label]

st.divider()

# --- Neuen Stand eintragen ---
with st.expander("Neuen Zählerstand eintragen", expanded=True):
    with st.form("new_reading"):
        col1, col2 = st.columns(2)
        with col1:
            reading_date = st.date_input("Datum", value=date.today())
            value = st.number_input(
                f"Zählerstand ({meter.unit})", min_value=0.0, step=0.01, format="%.2f"
            )
        with col2:
            note = st.text_area("Notiz", placeholder="optional")

        submitted = st.form_submit_button("Eintragen", type="primary")
        if submitted:
            existing = (
                session.query(Reading)
                .filter(Reading.meter_id == meter.id, Reading.reading_date == reading_date)
                .first()
            )
            if existing:
                st.error(f"Es existiert bereits ein Eintrag für {reading_date.strftime('%d.%m.%Y')}.")
            else:
                new_reading = Reading(
                    meter_id=meter.id,
                    reading_date=reading_date,
                    value=value,
                    note=note or None,
                )
                session.add(new_reading)
                session.commit()
                st.success(f"Zählerstand {value} {meter.unit} am {reading_date.strftime('%d.%m.%Y')} eingetragen.")
                st.rerun()

st.divider()

# --- Alle Stände anzeigen und bearbeiten ---
st.subheader(f"Alle Stände: {meter.name}")

readings = (
    session.query(Reading)
    .filter(Reading.meter_id == meter.id)
    .order_by(Reading.reading_date.desc())
    .all()
)

if not readings:
    st.info("Noch keine Stände eingetragen.")
else:
    df_raw = pd.DataFrame(
        [{"reading_date": r.reading_date, "value": r.value} for r in readings]
    )
    df_consumption = compute_consumption(df_raw.sort_values("reading_date"))

    consumption_map = dict(
        zip(df_consumption["reading_date"], df_consumption["consumption"])
    )

    for reading in readings:
        cons = consumption_map.get(reading.reading_date)
        cons_str = f"{cons:+.2f} {meter.unit}" if cons is not None else "—"
        label = f"{reading.reading_date.strftime('%d.%m.%Y')} | {reading.value:,.2f} {meter.unit} | Verbrauch: {cons_str}"

        with st.expander(label):
            with st.form(f"edit_reading_{reading.id}"):
                col1, col2 = st.columns(2)
                with col1:
                    e_date = st.date_input("Datum", value=reading.reading_date, key=f"d_{reading.id}")
                    e_value = st.number_input(
                        f"Wert ({meter.unit})",
                        value=float(reading.value),
                        step=0.01,
                        format="%.2f",
                        key=f"v_{reading.id}",
                    )
                with col2:
                    e_note = st.text_area("Notiz", value=reading.note or "", key=f"no_{reading.id}")

                col_save, col_del = st.columns(2)
                with col_save:
                    save = st.form_submit_button("Speichern", type="primary")
                with col_del:
                    delete = st.form_submit_button("Löschen", type="secondary")

                if save:
                    reading.reading_date = e_date
                    reading.value = e_value
                    reading.note = e_note or None
                    session.commit()
                    st.success("Gespeichert.")
                    st.rerun()

                if delete:
                    session.delete(reading)
                    session.commit()
                    st.success("Eintrag gelöscht.")
                    st.rerun()

session.close()
