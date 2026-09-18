import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import streamlit as st

from zaehler.database import create_manual_backup, get_backup_dir, get_db_path, get_session
from zaehler.models import Meter, Price, Reading

st.set_page_config(page_title="Daten & Sicherung", page_icon="🗄️", layout="wide")
st.title("Daten & Sicherung")
st.markdown(
    "Beim Start der App wird automatisch ein Backup der Datenbank angelegt "
    "(die letzten 30 Backups werden aufbewahrt). Hier kannst du zusätzlich "
    "manuell sichern oder Daten exportieren."
)

session = get_session()

st.divider()

# --- Datenbank-Backup ---
st.subheader("Datenbank")

col1, col2 = st.columns(2)
with col1:
    db_path = get_db_path()
    if db_path.exists():
        with open(db_path, "rb") as f:
            st.download_button(
                "📥 Datenbank herunterladen (.db)",
                data=f.read(),
                file_name="zaehler.db",
                mime="application/octet-stream",
            )
    else:
        st.info("Noch keine Datenbankdatei vorhanden.")

with col2:
    if st.button("🔒 Jetzt manuelles Backup erstellen"):
        backup_path = create_manual_backup()
        st.success(f"Backup erstellt: {backup_path.name}")
        st.rerun()

st.markdown("**Automatische Backups**")
backup_dir = get_backup_dir()
backups = sorted(backup_dir.glob("zaehler_*.db"), reverse=True)

if not backups:
    st.info("Noch keine Backups vorhanden.")
else:
    for backup in backups[:15]:
        b_col1, b_col2 = st.columns([4, 1])
        with b_col1:
            size_kb = backup.stat().st_size / 1024
            st.caption(f"{backup.name} ({size_kb:,.1f} KB)")
        with b_col2:
            with open(backup, "rb") as f:
                st.download_button(
                    "Herunterladen",
                    data=f.read(),
                    file_name=backup.name,
                    mime="application/octet-stream",
                    key=f"dl_{backup.name}",
                )
    if len(backups) > 15:
        st.caption(f"… und {len(backups) - 15} weitere ältere Backups im Verzeichnis `data/backups/`.")

st.divider()

# --- CSV-Export ---
st.subheader("CSV-Export")

meters = session.query(Meter).order_by(Meter.name).all()

if not meters:
    st.info("Keine Zähler vorhanden.")
else:
    readings = (
        session.query(Reading, Meter)
        .join(Meter, Reading.meter_id == Meter.id)
        .order_by(Meter.name, Reading.reading_date)
        .all()
    )
    readings_df = pd.DataFrame(
        [
            {
                "Zähler": meter.name,
                "Typ": meter.meter_type.value,
                "Zählernummer": meter.meter_number,
                "Datum": r.reading_date,
                "Wert": r.value,
                "Einheit": meter.unit,
                "Notiz": r.note,
            }
            for r, meter in readings
        ]
    )

    prices = (
        session.query(Price, Meter)
        .join(Meter, Price.meter_id == Meter.id)
        .order_by(Meter.name, Price.valid_from)
        .all()
    )
    prices_df = pd.DataFrame(
        [
            {
                "Zähler": meter.name,
                "Gültig ab": p.valid_from,
                "Arbeitspreis (€/kWh)": p.price_per_unit,
                "Grundgebühr (€/Monat)": p.base_price_per_month,
                "Brennwert": p.brennwert,
                "Z-Zahl": p.z_zahl,
                "Notiz": p.note,
            }
            for p, meter in prices
        ]
    )

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 Alle Zählerstände als CSV",
            data=readings_df.to_csv(index=False).encode("utf-8"),
            file_name="zaehlerstaende.csv",
            mime="text/csv",
            disabled=readings_df.empty,
        )
    with col2:
        st.download_button(
            "📥 Alle Preise als CSV",
            data=prices_df.to_csv(index=False).encode("utf-8"),
            file_name="preise.csv",
            mime="text/csv",
            disabled=prices_df.empty,
        )

session.close()
