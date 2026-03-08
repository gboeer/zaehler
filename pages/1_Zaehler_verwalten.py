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
TYPE_ICONS = {"Strom": "⚡", "Gas": "🔥", "Wasser": "💧"}


def edit_meter_form(meter: Meter, all_meters: list, session):
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

            # Elternauswahl: nicht sich selbst oder eigene Kinder
            child_ids = {m.id for m in all_meters if m.parent_id == meter.id}
            candidates = [m for m in all_meters if m.id != meter.id and m.id not in child_ids]
            parent_options = {"— kein (Hauptzähler)": None} | {
                f"{m.name} ({m.meter_number or 'Nr. unbekannt'})": m.id
                for m in candidates
            }
            current_label = next(
                (k for k, v in parent_options.items() if v == meter.parent_id),
                "— kein (Hauptzähler)",
            )
            e_parent_label = st.selectbox(
                "Übergeordneter Zähler",
                list(parent_options.keys()),
                index=list(parent_options.keys()).index(current_label),
                key=f"par_{meter.id}",
            )
            e_parent_id = parent_options[e_parent_label]

        col_save, col_del = st.columns(2)
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
            meter.parent_id = e_parent_id
            session.commit()
            st.success("Gespeichert.")
            st.rerun()

        if delete:
            has_children = any(m.parent_id == meter.id for m in all_meters)
            if has_children:
                st.error("Zähler hat noch Unterzähler — bitte diese zuerst löschen oder umhängen.")
            else:
                session.delete(meter)
                session.commit()
                st.success(f"Zähler **{meter.name}** gelöscht.")
                st.rerun()


# --- Neuen Zähler anlegen ---
with st.expander("Neuen Zähler anlegen", expanded=False):
    all_meters_for_form = session.query(Meter).order_by(Meter.name).all()

    with st.form("new_meter"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name", placeholder="z.B. Haushaltsstrom")
            meter_type = st.selectbox("Typ", [t.value for t in MeterType])
            meter_number = st.text_input("Zählernummer", placeholder="optional")
        with col2:
            unit = st.text_input("Einheit", value=UNITS.get(meter_type, "kWh"))
            location = st.text_input("Standort", placeholder="optional, z.B. Keller")
            parent_options_new = {"— kein (Hauptzähler)": None} | {
                f"{m.name} ({m.meter_number or 'Nr. unbekannt'})": m.id
                for m in all_meters_for_form
            }
            parent_label_new = st.selectbox("Übergeordneter Zähler", list(parent_options_new.keys()))
            parent_id_new = parent_options_new[parent_label_new]

        submitted = st.form_submit_button("Zähler anlegen", type="primary")
        if submitted:
            if not name:
                st.error("Bitte einen Namen eingeben.")
            else:
                session.add(Meter(
                    name=name,
                    meter_type=MeterType(meter_type),
                    meter_number=meter_number or None,
                    unit=unit,
                    location=location or None,
                    active=1,
                    parent_id=parent_id_new,
                ))
                session.commit()
                st.success(f"Zähler **{name}** wurde angelegt.")
                st.rerun()

st.divider()

# --- Baumansicht ---
st.subheader("Zählerstruktur")

all_meters = session.query(Meter).order_by(Meter.name).all()
hauptzaehler = [m for m in all_meters if m.parent_id is None]

if not hauptzaehler:
    st.info("Noch keine Zähler vorhanden.")
else:
    for hm in hauptzaehler:
        icon = TYPE_ICONS.get(hm.meter_type.value, "📊")
        status = "✅" if hm.active else "❌"
        unterzaehler = [m for m in all_meters if m.parent_id == hm.id]
        header = f"{status} {icon} **{hm.name}** ({hm.meter_type.value})"
        if unterzaehler:
            header += f"  —  {len(unterzaehler)} Unterzähler"

        with st.expander(header, expanded=True):
            st.markdown("**Hauptzähler bearbeiten:**")
            edit_meter_form(hm, all_meters, session)

            if unterzaehler:
                st.divider()
                st.markdown("**Unterzähler:**")
                for um in unterzaehler:
                    sub_icon = TYPE_ICONS.get(um.meter_type.value, "📊")
                    sub_status = "✅" if um.active else "❌"
                    with st.expander(f"{sub_status} {sub_icon} {um.name}", expanded=False):
                        edit_meter_form(um, all_meters, session)

session.close()
