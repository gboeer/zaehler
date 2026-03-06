import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import date

import pandas as pd
import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, MeterType, Price

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
is_gas = meter.meter_type == MeterType.GAS

if is_gas:
    st.info(
        "**Gas-Abrechnung:** Der Zähler misst in m³. "
        "Die Umrechnung erfolgt via: **kWh = m³ × Z-Zahl × Brennwert (Hs)**. "
        "Der Arbeitspreis gilt pro kWh."
    )

st.divider()

# --- Neuen Preis eintragen ---
with st.expander("Neuen Preis eintragen", expanded=True):
    with st.form("new_price"):
        col1, col2 = st.columns(2)
        with col1:
            valid_from = st.date_input("Gültig ab", value=date.today())
            # Gas-Preis: ct/kWh eingeben, intern als €/kWh speichern
            if is_gas:
                price_ct = st.number_input(
                    "Arbeitspreis (ct/kWh)",
                    min_value=0.0,
                    value=10.58,
                    step=0.01,
                    format="%.4f",
                    help="Preis wie auf der Gasrechnung in Cent pro kWh angegeben",
                )
                price_per_unit = price_ct / 100.0  # intern €/kWh
            else:
                price_ct_eur = st.number_input(
                    f"Arbeitspreis (ct/kWh)" if meter.unit == "kWh" else f"Arbeitspreis (€/{meter.unit})",
                    min_value=0.0,
                    value=30.0 if meter.unit == "kWh" else 0.30,
                    step=0.01,
                    format="%.4f",
                )
                price_per_unit = price_ct_eur / 100.0 if meter.unit == "kWh" else price_ct_eur

        with col2:
            base_price = st.number_input(
                "Grundgebühr (€/Monat)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
            )
            note = st.text_input("Notiz", placeholder="optional, z.B. Tarifname")

        # Gas-spezifisch: Brennwert und Z-Zahl
        brennwert = None
        z_zahl = None
        if is_gas:
            st.markdown("**Umrechnungsfaktoren** (stehen auf der Gasrechnung)")
            gc1, gc2 = st.columns(2)
            with gc1:
                brennwert = st.number_input(
                    "Brennwert Hs (kWh/m³)",
                    min_value=0.0,
                    value=10.0,
                    step=0.001,
                    format="%.3f",
                    help="Oberer Heizwert, z.B. 10.317 kWh/m³",
                )
            with gc2:
                z_zahl = st.number_input(
                    "Zustandszahl (Z)",
                    min_value=0.0,
                    value=0.9640,
                    step=0.0001,
                    format="%.4f",
                    help="Zustandszahl für Druck- und Temperaturkorrektur, z.B. 0.9640",
                )
            st.caption(
                f"Umrechnungsfaktor: {brennwert:.3f} × {z_zahl:.4f} = "
                f"**{brennwert * z_zahl:.4f} kWh/m³**"
            )

        submitted = st.form_submit_button("Preis speichern", type="primary")
        if submitted:
            new_price = Price(
                meter_id=meter.id,
                valid_from=valid_from,
                price_per_unit=price_per_unit,
                base_price_per_month=base_price,
                brennwert=brennwert,
                z_zahl=z_zahl,
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
        row = {
            "Gültig ab": p.valid_from.strftime("%d.%m.%Y"),
            "Arbeitspreis (ct/kWh)": f"{p.price_per_unit * 100:.4f}",
            "Grundgebühr (€/Mon.)": f"{p.base_price_per_month:.2f}",
        }
        if is_gas:
            row["Brennwert Hs (kWh/m³)"] = f"{p.brennwert:.3f}" if p.brennwert else "—"
            row["Z-Zahl"] = f"{p.z_zahl:.4f}" if p.z_zahl else "—"
            if p.brennwert and p.z_zahl:
                row["Faktor (kWh/m³)"] = f"{p.brennwert * p.z_zahl:.4f}"
        row["Notiz"] = p.note or ""
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader("Bearbeiten / Löschen")
    for price in prices:
        ct_display = price.price_per_unit * 100
        label = (
            f"ab {price.valid_from.strftime('%d.%m.%Y')} | "
            f"{ct_display:.4f} ct/kWh | "
            f"Grundgeb. {price.base_price_per_month:.2f} €/Mon."
        )
        if is_gas and price.brennwert and price.z_zahl:
            label += f" | Hs={price.brennwert:.3f} Z={price.z_zahl:.4f}"

        with st.expander(label):
            with st.form(f"edit_price_{price.id}"):
                col1, col2 = st.columns(2)
                with col1:
                    e_from = st.date_input("Gültig ab", value=price.valid_from, key=f"vf_{price.id}")
                    e_ct = st.number_input(
                        "Arbeitspreis (ct/kWh)",
                        value=float(price.price_per_unit * 100),
                        step=0.01,
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

                if is_gas:
                    gc1, gc2 = st.columns(2)
                    with gc1:
                        e_brennwert = st.number_input(
                            "Brennwert Hs (kWh/m³)",
                            value=float(price.brennwert) if price.brennwert else 10.0,
                            step=0.001,
                            format="%.3f",
                            key=f"bw_{price.id}",
                        )
                    with gc2:
                        e_z = st.number_input(
                            "Zustandszahl (Z)",
                            value=float(price.z_zahl) if price.z_zahl else 0.9640,
                            step=0.0001,
                            format="%.4f",
                            key=f"zz_{price.id}",
                        )

                col_save, col_del = st.columns(2)
                with col_save:
                    save = st.form_submit_button("Speichern", type="primary")
                with col_del:
                    delete = st.form_submit_button("Löschen", type="secondary")

                if save:
                    price.valid_from = e_from
                    price.price_per_unit = e_ct / 100.0
                    price.base_price_per_month = e_base
                    price.note = e_note or None
                    if is_gas:
                        price.brennwert = e_brennwert
                        price.z_zahl = e_z
                    session.commit()
                    st.success("Gespeichert.")
                    st.rerun()

                if delete:
                    session.delete(price)
                    session.commit()
                    st.success("Preis gelöscht.")
                    st.rerun()

session.close()
