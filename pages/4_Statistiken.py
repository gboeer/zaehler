import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import plotly.express as px
import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, MeterType, Price, Reading
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
is_gas = meter.meter_type == MeterType.GAS

# Unterzähler des gewählten Zählers
children = [m for m in meters if m.parent_id == meter.id]
has_children = len(children) > 0

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

# --- Zeitraum-Filter (Sidebar) ---
st.sidebar.header("Zeitraum")
min_date = df["reading_date"].min()
max_date = df["reading_date"].max()
date_from = st.sidebar.date_input("Von", value=min_date, min_value=min_date, max_value=max_date)
date_to = st.sidebar.date_input("Bis", value=max_date, min_value=min_date, max_value=max_date)

df_filtered = df_valid[
    (df_valid["reading_date"] >= date_from) & (df_valid["reading_date"] <= date_to)
]

agg_label = st.sidebar.selectbox("Aggregation", ["Rohdaten", "Monatlich", "Quartal", "Jährlich"])
freq_map = {"Monatlich": "ME", "Quartal": "QE", "Jährlich": "YE"}

# --- Tabs: Verbrauch | Aufteilung (nur bei Hauptzähler mit Unterzählern) ---
if has_children:
    tab_verbrauch, tab_aufteilung = st.tabs(["Verbrauchsverlauf", "Aufteilung nach Unterzählern"])
else:
    tab_verbrauch = st.container()
    tab_aufteilung = None


# =========================================================
# TAB 1: Verbrauchsverlauf (immer sichtbar)
# =========================================================
with tab_verbrauch:
    # Kennzahlen
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

    # Kosten
    prices = session.query(Price).filter(Price.meter_id == meter.id).all()
    if prices:
        prices_df = pd.DataFrame(
            [
                {
                    "valid_from": p.valid_from,
                    "price_per_unit": p.price_per_unit,
                    "base_price_per_month": p.base_price_per_month,
                    "brennwert": p.brennwert,
                    "z_zahl": p.z_zahl,
                }
                for p in prices
            ]
        )
        total_days = int(df_filtered["days"].sum()) if "days" in df_filtered.columns else None
        cost_info = compute_costs(total, date_to, prices_df, days=total_days, is_gas=is_gas)
        if cost_info["total_cost"] is not None:
            st.subheader("Kosten (Schätzung)")
            if is_gas and cost_info["kwh"] is not None:
                st.caption(
                    f"Umrechnung: {total:,.2f} m³ × {cost_info['z_zahl']:.4f} (Z) × "
                    f"{cost_info['brennwert']:.3f} (Hs) = **{cost_info['kwh']:,.2f} kWh**"
                )
                col1.metric("Gesamtverbrauch (kWh)", f"{cost_info['kwh']:,.2f} kWh")
            c1, c2, c3 = st.columns(3)
            c1.metric("Arbeitskosten", f"{cost_info['consumption_cost']:,.2f} €")
            c2.metric("Grundgebühr (Periode)", f"{cost_info['base_price']:,.2f} €")
            c3.metric("Gesamt", f"{cost_info['total_cost']:,.2f} €")

    st.divider()

    # Verbrauchsdiagramm
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

    # Zählerstandsverlauf
    st.subheader("Zählerstandsverlauf")
    df_vals = df[["reading_date", "value"]].copy()
    df_vals = df_vals[
        (df_vals["reading_date"] >= date_from) & (df_vals["reading_date"] <= date_to)
    ]
    fig2 = px.line(
        df_vals,
        x="reading_date",
        y="value",
        markers=True,
        labels={"reading_date": "Datum", "value": f"Stand ({meter.unit})"},
    )
    fig2.update_layout(margin=dict(t=20, b=20))
    st.plotly_chart(fig2, use_container_width=True)

    # Rohdaten
    with st.expander("Rohdaten anzeigen"):
        display_df = df_filtered[
            ["reading_date", "value", "prev_value", "consumption", "days", "daily_avg"]
        ].copy()
        display_df.columns = [
            "Datum",
            f"Stand ({meter.unit})",
            f"Vorstand ({meter.unit})",
            f"Verbrauch ({meter.unit})",
            "Tage",
            f"Ø/Tag ({meter.unit})",
        ]
        display_df["Datum"] = display_df["Datum"].apply(lambda d: d.strftime("%d.%m.%Y"))
        st.dataframe(display_df, use_container_width=True, hide_index=True)


# =========================================================
# TAB 2: Aufteilung nach Unterzählern
# =========================================================
if has_children and tab_aufteilung is not None:
    with tab_aufteilung:
        st.subheader(f"Aufteilung: {meter.name}")
        st.caption(
            f"Zeitraum: {date_from.strftime('%d.%m.%Y')} – {date_to.strftime('%d.%m.%Y')}"
        )

        # Verbrauch Hauptzähler im Zeitraum
        parent_total = df_filtered["consumption"].sum()

        # Verbrauch je Unterzähler im gleichen Zeitraum berechnen
        child_data = []
        for child in children:
            child_readings = (
                session.query(Reading)
                .filter(Reading.meter_id == child.id)
                .order_by(Reading.reading_date)
                .all()
            )
            if len(child_readings) < 2:
                child_data.append({"name": child.name, "consumption": 0.0, "unit": child.unit})
                continue

            cdf = pd.DataFrame(
                [{"reading_date": r.reading_date, "value": r.value} for r in child_readings]
            )
            cdf = compute_consumption(cdf)
            cdf = cdf.dropna(subset=["consumption"])
            cdf_filtered = cdf[
                (cdf["reading_date"] >= date_from) & (cdf["reading_date"] <= date_to)
            ]
            child_total = cdf_filtered["consumption"].sum()
            child_data.append({
                "name": child.name,
                "consumption": child_total,
                "unit": child.unit,
                "df": cdf_filtered,
            })

        sub_total = sum(c["consumption"] for c in child_data)
        sonstiges = max(0.0, parent_total - sub_total)

        # Kennzahlen
        cols = st.columns(len(child_data) + 2)
        cols[0].metric(
            f"Gesamt ({meter.name})",
            f"{parent_total:,.2f} {meter.unit}",
        )
        for i, c in enumerate(child_data):
            pct = (c["consumption"] / parent_total * 100) if parent_total > 0 else 0
            cols[i + 1].metric(
                c["name"],
                f"{c['consumption']:,.2f} {c['unit']}",
                f"{pct:.1f} %",
            )
        sonstiges_pct = (sonstiges / parent_total * 100) if parent_total > 0 else 0
        cols[-1].metric("Sonstiges / nicht gemessen", f"{sonstiges:,.2f} {meter.unit}", f"{sonstiges_pct:.1f} %")

        st.divider()

        # Kreisdiagramm
        pie_data = [{"Zähler": c["name"], "Verbrauch": c["consumption"]} for c in child_data]
        if sonstiges > 0:
            pie_data.append({"Zähler": "Sonstiges", "Verbrauch": sonstiges})

        pie_df = pd.DataFrame(pie_data)
        if not pie_df.empty and pie_df["Verbrauch"].sum() > 0:
            fig_pie = px.pie(
                pie_df,
                names="Zähler",
                values="Verbrauch",
                title=f"Aufteilung des Gesamtverbrauchs ({meter.unit})",
                hole=0.35,
            )
            fig_pie.update_traces(textinfo="label+percent+value")
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()

        # Stacked Bar über Zeit
        st.subheader("Verbrauch über Zeit (gestapelt)")

        if agg_label == "Rohdaten":
            # Einfache Aggregation auf monatlich für bessere Visualisierung
            resample_freq = "ME"
        else:
            resample_freq = freq_map[agg_label]

        stacked_frames = []
        for c in child_data:
            if "df" not in c or c["df"].empty:
                continue
            resampled = resample_consumption(c["df"], freq=resample_freq)
            if resampled.empty:
                continue
            resampled["Zähler"] = c["name"]
            stacked_frames.append(resampled)

        # "Sonstiges" als eigene Reihe
        if stacked_frames:
            parent_resampled = resample_consumption(df_filtered, freq=resample_freq)
            if not parent_resampled.empty:
                all_periods = parent_resampled["period"].tolist()
                combined = pd.concat(stacked_frames, ignore_index=True)
                child_by_period = combined.groupby("period")["consumption"].sum()
                sonstiges_series = parent_resampled.set_index("period")["consumption"] - child_by_period
                sonstiges_df = sonstiges_series.clip(lower=0).reset_index()
                sonstiges_df.columns = ["period", "consumption"]
                sonstiges_df["Zähler"] = "Sonstiges"
                stacked_frames.append(sonstiges_df)

                stacked = pd.concat(stacked_frames, ignore_index=True)
                fig_stack = px.bar(
                    stacked,
                    x="period",
                    y="consumption",
                    color="Zähler",
                    barmode="stack",
                    labels={"period": "Zeitraum", "consumption": f"Verbrauch ({meter.unit})"},
                )
                fig_stack.update_layout(margin=dict(t=20, b=20))
                st.plotly_chart(fig_stack, use_container_width=True)
        else:
            st.info("Zu wenig Daten der Unterzähler für die Zeitreihe.")

session.close()
