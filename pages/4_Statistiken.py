import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from zaehler.database import get_session
from zaehler.models import Meter, MeterType, Price, Reading
from zaehler.utils.calculations import (
    compute_consumption,
    compute_costs,
    interpolate_daily,
    resample_daily,
    rolling_daily_avg,
)

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

# Rohdaten als DataFrame
df_raw = pd.DataFrame([{"reading_date": r.reading_date, "value": r.value} for r in readings])

# Tägliche Interpolation (Basis für alle Plots)
daily_df = interpolate_daily(df_raw)

# Perioden-Verbrauch (für Kennzahlen)
df_periods = compute_consumption(df_raw)
df_periods_valid = df_periods.dropna(subset=["consumption"])

# --- Zeitraum-Filter (Sidebar) ---
st.sidebar.header("Zeitraum")
min_date = daily_df["date"].min().date()
max_date = daily_df["date"].max().date()
date_from = st.sidebar.date_input("Von", value=min_date, min_value=min_date, max_value=max_date)
date_to = st.sidebar.date_input("Bis", value=max_date, min_value=min_date, max_value=max_date)

daily_filtered = daily_df[
    (daily_df["date"].dt.date >= date_from) & (daily_df["date"].dt.date <= date_to)
].copy()

# Glättungsfenster
st.sidebar.header("Glättung")
window_options = {"7 Tage": 7, "14 Tage": 14, "30 Tage": 30, "90 Tage": 90}
window_label = st.sidebar.selectbox("Gleitender Durchschnitt", list(window_options.keys()), index=2)
window = window_options[window_label]

# Aggregation für Balkendiagramme
st.sidebar.header("Aggregation")
agg_label = st.sidebar.selectbox("Zeitraum-Aggregation", ["Monatlich", "Quartal", "Jährlich"])
freq_map = {"Monatlich": "ME", "Quartal": "QE", "Jährlich": "YE"}
freq = freq_map[agg_label]

# --- Tabs ---
if has_children:
    tab_verlauf, tab_taeglich, tab_aufteilung = st.tabs([
        "Verlauf & Aggregation", "Täglicher Verbrauch", "Aufteilung nach Unterzählern"
    ])
else:
    tab_verlauf, tab_taeglich = st.tabs(["Verlauf & Aggregation", "Täglicher Verbrauch"])
    tab_aufteilung = None


# =========================================================
# TAB 1: Verlauf & Aggregation
# =========================================================
with tab_verlauf:
    # Kennzahlen aus täglichen Daten
    st.subheader("Kennzahlen")
    total = daily_filtered["daily_consumption"].sum()
    span_days = (daily_filtered["date"].max() - daily_filtered["date"].min()).days + 1
    avg_daily_val = daily_filtered["daily_consumption"].mean()

    # Monatliche Werte für Max/Min
    monthly = resample_daily(daily_filtered, freq="ME")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Gesamtverbrauch", f"{total:,.2f} {meter.unit}")
    col2.metric("Ø pro Tag", f"{avg_daily_val:.3f} {meter.unit}/Tag")
    col3.metric(
        "Höchster Monat",
        f"{monthly['consumption'].max():,.2f} {meter.unit}" if not monthly.empty else "—",
    )
    col4.metric(
        "Niedrigster Monat",
        f"{monthly['consumption'].min():,.2f} {meter.unit}" if not monthly.empty else "—",
    )

    # Kosten
    prices = session.query(Price).filter(Price.meter_id == meter.id).all()
    if prices:
        prices_df = pd.DataFrame(
            [{
                "valid_from": p.valid_from,
                "price_per_unit": p.price_per_unit,
                "base_price_per_month": p.base_price_per_month,
                "brennwert": p.brennwert,
                "z_zahl": p.z_zahl,
            } for p in prices]
        )
        cost_info = compute_costs(total, date_to, prices_df, days=span_days, is_gas=is_gas)
        if cost_info["total_cost"] is not None:
            st.subheader("Kosten (Schätzung)")
            if is_gas and cost_info["kwh"] is not None:
                st.caption(
                    f"Umrechnung: {total:,.2f} m³ × {cost_info['z_zahl']:.4f} (Z) × "
                    f"{cost_info['brennwert']:.3f} (Hs) = **{cost_info['kwh']:,.2f} kWh**"
                )
            c1, c2, c3 = st.columns(3)
            c1.metric("Arbeitskosten", f"{cost_info['consumption_cost']:,.2f} €")
            c2.metric("Grundgebühr (Periode)", f"{cost_info['base_price']:,.2f} €")
            c3.metric("Gesamt", f"{cost_info['total_cost']:,.2f} €")

    st.divider()

    # Aggregiertes Balkendiagramm (interpolationsbasiert)
    st.subheader(f"Verbrauch {agg_label}")
    agg_df = resample_daily(daily_filtered, freq=freq)
    if not agg_df.empty:
        fig_bar = px.bar(
            agg_df,
            x="period",
            y="consumption",
            labels={"period": "Zeitraum", "consumption": f"Verbrauch ({meter.unit})"},
            color_discrete_sequence=["#1f77b4"],
        )
        # Durchschnittslinie
        avg_line = agg_df["consumption"].mean()
        fig_bar.add_hline(
            y=avg_line,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Ø {avg_line:.2f} {meter.unit}",
            annotation_position="top right",
        )
        fig_bar.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig_bar, use_container_width=True)

    # Zählerstandsverlauf
    st.subheader("Zählerstandsverlauf")
    vals_filtered = daily_filtered[["date", "value"]].copy()
    fig_val = px.line(
        vals_filtered,
        x="date",
        y="value",
        labels={"date": "Datum", "value": f"Stand ({meter.unit})"},
    )
    # Ablesung-Punkte hervorheben
    readings_in_range = df_raw[
        (pd.to_datetime(df_raw["reading_date"]).dt.date >= date_from)
        & (pd.to_datetime(df_raw["reading_date"]).dt.date <= date_to)
    ]
    fig_val.add_scatter(
        x=pd.to_datetime(readings_in_range["reading_date"]),
        y=readings_in_range["value"],
        mode="markers",
        marker=dict(size=8, color="red", symbol="circle"),
        name="Ablesungen",
    )
    fig_val.update_layout(margin=dict(t=20, b=20))
    st.plotly_chart(fig_val, use_container_width=True)


# =========================================================
# TAB 2: Täglicher Verbrauch (interpoliert + Rolling Avg)
# =========================================================
with tab_taeglich:
    st.subheader(f"Täglicher Verbrauch — gleitender Durchschnitt ({window_label})")
    st.caption(
        f"Die täglichen Werte werden **linear zwischen den Ablesungen interpoliert**. "
        f"Innerhalb einer Ablesungsperiode ist der Tagesverbrauch konstant (gleichmäßig verteilt). "
        f"Der gleitende Durchschnitt über {window} Tage glättet Sprünge an den Ablesungsgrenzen."
    )

    if len(daily_filtered) < 2:
        st.info("Zu wenig Daten im gewählten Zeitraum.")
    else:
        rolled = rolling_daily_avg(daily_filtered, window=window)

        fig_daily = go.Figure()

        # Rohe Tageswerte (sehr dünn, als Hintergrund)
        fig_daily.add_trace(go.Scatter(
            x=rolled["date"],
            y=rolled["daily_consumption"],
            mode="lines",
            name="Tageswert (interpoliert)",
            line=dict(color="lightsteelblue", width=1),
            opacity=0.5,
        ))

        # Gleitender Durchschnitt (dick, im Vordergrund)
        fig_daily.add_trace(go.Scatter(
            x=rolled["date"],
            y=rolled["rolling_avg"],
            mode="lines",
            name=f"Gleitender Ø ({window_label})",
            line=dict(color="#1f77b4", width=2.5),
        ))

        # Gesamtdurchschnitt als horizontale Linie
        overall_avg = daily_filtered["daily_consumption"].mean()
        fig_daily.add_hline(
            y=overall_avg,
            line_dash="dot",
            line_color="red",
            annotation_text=f"Gesamt-Ø {overall_avg:.3f} {meter.unit}/Tag",
            annotation_position="bottom right",
        )

        # Ablesungszeitpunkte als vertikale Markierungen
        readings_in_range = df_raw[
            (pd.to_datetime(df_raw["reading_date"]).dt.date >= date_from)
            & (pd.to_datetime(df_raw["reading_date"]).dt.date <= date_to)
        ]
        for _, row in readings_in_range.iterrows():
            fig_daily.add_vline(
                x=pd.Timestamp(row["reading_date"]),
                line_dash="dot",
                line_color="gray",
                line_width=1,
                opacity=0.4,
            )

        fig_daily.update_layout(
            xaxis_title="Datum",
            yaxis_title=f"{meter.unit}/Tag",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=40, b=20),
            hovermode="x unified",
        )
        st.plotly_chart(fig_daily, use_container_width=True)

        # Jahresvergleich (wenn Daten > 1 Jahr)
        if span_days > 400:
            st.subheader("Jahresvergleich (Ø pro Tag je Monat)")
            daily_filtered_copy = daily_filtered.copy()
            daily_filtered_copy["monat"] = daily_filtered_copy["date"].dt.month
            daily_filtered_copy["jahr"] = daily_filtered_copy["date"].dt.year
            monthly_avg = (
                daily_filtered_copy.groupby(["jahr", "monat"])["daily_consumption"]
                .mean()
                .reset_index()
            )
            monthly_avg["Monat"] = monthly_avg["monat"].apply(
                lambda m: ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                            "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"][m - 1]
            )
            monthly_avg["Jahr"] = monthly_avg["jahr"].astype(str)
            fig_year = px.line(
                monthly_avg,
                x="Monat",
                y="daily_consumption",
                color="Jahr",
                markers=True,
                labels={"daily_consumption": f"Ø {meter.unit}/Tag"},
                category_orders={"Monat": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                                            "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]},
            )
            fig_year.update_layout(margin=dict(t=20, b=20))
            st.plotly_chart(fig_year, use_container_width=True)


# =========================================================
# TAB 3: Aufteilung nach Unterzählern
# =========================================================
if has_children and tab_aufteilung is not None:
    with tab_aufteilung:
        st.subheader(f"Aufteilung: {meter.name}")
        st.caption(
            f"Zeitraum: {date_from.strftime('%d.%m.%Y')} – {date_to.strftime('%d.%m.%Y')}"
        )

        parent_total = daily_filtered["daily_consumption"].sum()

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

            c_raw = pd.DataFrame(
                [{"reading_date": r.reading_date, "value": r.value} for r in child_readings]
            )
            c_daily = interpolate_daily(c_raw)
            c_daily_filtered = c_daily[
                (c_daily["date"].dt.date >= date_from) & (c_daily["date"].dt.date <= date_to)
            ]
            child_total = c_daily_filtered["daily_consumption"].sum()
            child_data.append({
                "name": child.name,
                "consumption": child_total,
                "unit": child.unit,
                "daily": c_daily_filtered,
            })

        sub_total = sum(c["consumption"] for c in child_data)
        sonstiges = max(0.0, parent_total - sub_total)

        cols = st.columns(len(child_data) + 2)
        cols[0].metric(f"Gesamt ({meter.name})", f"{parent_total:,.2f} {meter.unit}")
        for i, c in enumerate(child_data):
            pct = (c["consumption"] / parent_total * 100) if parent_total > 0 else 0
            cols[i + 1].metric(c["name"], f"{c['consumption']:,.2f} {c['unit']}", f"{pct:.1f} %")
        sonstiges_pct = (sonstiges / parent_total * 100) if parent_total > 0 else 0
        cols[-1].metric("Sonstiges", f"{sonstiges:,.2f} {meter.unit}", f"{sonstiges_pct:.1f} %")

        st.divider()

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
        st.subheader("Verbrauch über Zeit (gestapelt)")

        stacked_frames = []
        for c in child_data:
            if "daily" not in c or c["daily"].empty:
                continue
            resampled = resample_daily(c["daily"], freq=freq)
            if resampled.empty:
                continue
            resampled["Zähler"] = c["name"]
            stacked_frames.append(resampled)

        if stacked_frames:
            parent_resampled = resample_daily(daily_filtered, freq=freq)
            if not parent_resampled.empty:
                combined = pd.concat(stacked_frames, ignore_index=True)
                child_by_period = combined.groupby("period")["consumption"].sum()
                sonstiges_df = parent_resampled.set_index("period")["consumption"].subtract(
                    child_by_period, fill_value=0
                ).clip(lower=0).reset_index()
                sonstiges_df.columns = ["period", "consumption"]
                sonstiges_df["Zähler"] = "Sonstiges"
                stacked_frames.append(sonstiges_df)
                stacked = pd.concat(stacked_frames, ignore_index=True)
                fig_stack = px.bar(
                    stacked, x="period", y="consumption", color="Zähler", barmode="stack",
                    labels={"period": "Zeitraum", "consumption": f"Verbrauch ({meter.unit})"},
                )
                fig_stack.update_layout(margin=dict(t=20, b=20))
                st.plotly_chart(fig_stack, use_container_width=True)
        else:
            st.info("Zu wenig Daten der Unterzähler für die Zeitreihe.")

session.close()
