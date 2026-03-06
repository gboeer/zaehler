import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import date

import pandas as pd
import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, Price

st.set_page_config(page_title="Preise", page_icon="💶", layout="wide")
st.title("Preise verwalten")

session = get_session()

meters = session.query(Meter).order_by(Meter.name).all()

if not meters:
    st.warning("Keine Zähler vorhanden. Bitte zuerst einen Zähler anlegen.")
    st.stop()

meter_options = {f"{m.name} ({m.meter_type.value})": m for m in meters}
selected_label = st.selectbox("Zähler auswählen", list(meter_options.keys()))
meter = meter_options[selected_label]

st.divider()

# --- Neuen Preis eintragen ---
with st.expander("Neuen Preis eintragen", expanded=True):
    with st.form("new_price"):
        col1, col2 = st.columns(2)
        with col1:
            valid_from = st.date_input("Gültig ab", value=date.today())
            price_per_unit = st.number_input(
                f"Arbeitspreis (€/{meter.unit})",
                min_value=0.0,
                value=0.30,
                step=0.001,
                format="%.4f",
            )
        with col2:
            base_price = st.number_input(
                "Grundgebühr (€/Monat)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
            )
            note = st.text_input("Notiz", placeholder="optional, z.B. Tarifname")

        submitted = st.form_submit_button("Preis speichern", type="primary")
        if submitted:
            new_price = Price(
                meter_id=meter.id,
                valid_from=valid_from,
                price_per_unit=price_per_unit,
                base_price_per_month=base_price,
                note=note or None,
            )
            session.add(new_price)
            session.commit()
            st.success(f"Preis ab {valid_from.strftime('%d.%m.%Y')} gespeichert.")
            st.rerun()

st.divider()

# --- Preisübersicht ---
st.subheader(f"Preishistorie: {meter.name}")

prices = (
    session.query(Price)
    .filter(Price.meter_id == meter.id)
    .order_by(Price.valid_from.desc())
    .all()
)

if not prices:
    st.info("Noch keine Preise eingetragen.")
else:
    rows = []
    for p in prices:
        rows.append(
            {
                "Gültig ab": p.valid_from.strftime("%d.%m.%Y"),
                f"Arbeitspreis (€/{meter.unit})": f"{p.price_per_unit:.4f}",
                "Grundgebühr (€/Mon.)": f"{p.base_price_per_month:.2f}",
                "Notiz": p.note or "",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader("Bearbeiten / Löschen")
    for price in prices:
        label = (
            f"ab {price.valid_from.strftime('%d.%m.%Y')} | "
            f"{price.price_per_unit:.4f} €/{meter.unit} | "
            f"Grundgeb. {price.base_price_per_month:.2f} €/Mon."
        )
        with st.expander(label):
            with st.form(f"edit_price_{price.id}"):
                col1, col2 = st.columns(2)
                with col1:
                    e_from = st.date_input("Gültig ab", value=price.valid_from, key=f"vf_{price.id}")
                    e_ppu = st.number_input(
                        f"Arbeitspreis (€/{meter.unit})",
                        value=float(price.price_per_unit),
                        step=0.001,
                        format="%.4f",
                        key=f"ppu_{price.id}",
                    )
                with col2:
                    e_base = st.number_input(
                        "Grundgebühr (€/Mon.)",
                        value=float(price.base_price_per_month),
                        step=0.01,
                        format="%.2f",
                        key=f"bp_{price.id}",
                    )
                    e_note = st.text_input("Notiz", value=price.note or "", key=f"pn_{price.id}")

                col_save, col_del = st.columns(2)
                with col_save:
                    save = st.form_submit_button("Speichern", type="primary")
                with col_del:
                    delete = st.form_submit_button("Löschen", type="secondary")

                if save:
                    price.valid_from = e_from
                    price.price_per_unit = e_ppu
                    price.base_price_per_month = e_base
                    price.note = e_note or None
                    session.commit()
                    st.success("Gespeichert.")
                    st.rerun()

                if delete:
                    session.delete(price)
                    session.commit()
                    st.success("Preis gelöscht.")
                    st.rerun()

session.close()
