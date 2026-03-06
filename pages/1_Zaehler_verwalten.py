import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, MeterType

st.set_page_config(page_title="Zähler verwalten", page_icon="📋", layout="wide")
st.title("Zähler verwalten")

session = get_session()

UNITS = {"Strom": "kWh", "Gas": "m³", "Wasser": "m³"}

# --- Neuen Zähler anlegen ---
with st.expander("Neuen Zähler anlegen", expanded=False):
    with st.form("new_meter"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name", placeholder="z.B. Haushaltsstrom")
            meter_type = st.selectbox("Typ", [t.value for t in MeterType])
            meter_number = st.text_input("Zählernummer", placeholder="optional")
        with col2:
            unit = st.text_input("Einheit", value=UNITS.get(meter_type, "kWh"))
            location = st.text_input("Standort", placeholder="optional, z.B. Keller")

        submitted = st.form_submit_button("Zähler anlegen", type="primary")
        if submitted:
            if not name:
                st.error("Bitte einen Namen eingeben.")
            else:
                new_meter = Meter(
                    name=name,
                    meter_type=MeterType(meter_type),
                    meter_number=meter_number or None,
                    unit=unit,
                    location=location or None,
                    active=1,
                )
                session.add(new_meter)
                session.commit()
                st.success(f"Zähler **{name}** wurde angelegt.")
                st.rerun()

st.divider()

# --- Zählerübersicht & Bearbeitung ---
st.subheader("Vorhandene Zähler")

meters = session.query(Meter).order_by(Meter.active.desc(), Meter.name).all()

if not meters:
    st.info("Noch keine Zähler vorhanden.")
else:
    for meter in meters:
        status_icon = "✅" if meter.active else "❌"
        with st.expander(f"{status_icon} {meter.name} ({meter.meter_type.value})"):
            with st.form(f"edit_meter_{meter.id}"):
                col1, col2 = st.columns(2)
                with col1:
                    e_name = st.text_input("Name", value=meter.name, key=f"n_{meter.id}")
                    e_type = st.selectbox(
                        "Typ",
                        [t.value for t in MeterType],
                        index=[t.value for t in MeterType].index(meter.meter_type.value),
                        key=f"t_{meter.id}",
                    )
                    e_number = st.text_input(
                        "Zählernummer", value=meter.meter_number or "", key=f"mn_{meter.id}"
                    )
                with col2:
                    e_unit = st.text_input("Einheit", value=meter.unit, key=f"u_{meter.id}")
                    e_location = st.text_input(
                        "Standort", value=meter.location or "", key=f"l_{meter.id}"
                    )
                    e_active = st.checkbox("Aktiv", value=bool(meter.active), key=f"a_{meter.id}")

                col_save, col_del = st.columns([1, 1])
                with col_save:
                    save = st.form_submit_button("Speichern", type="primary")
                with col_del:
                    delete = st.form_submit_button("Löschen", type="secondary")

                if save:
                    meter.name = e_name
                    meter.meter_type = MeterType(e_type)
                    meter.meter_number = e_number or None
                    meter.unit = e_unit
                    meter.location = e_location or None
                    meter.active = 1 if e_active else 0
                    session.commit()
                    st.success("Gespeichert.")
                    st.rerun()

                if delete:
                    session.delete(meter)
                    session.commit()
                    st.success(f"Zähler **{meter.name}** gelöscht.")
                    st.rerun()

session.close()
