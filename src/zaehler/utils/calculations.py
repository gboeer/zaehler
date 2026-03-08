from datetime import date
from typing import Optional

import pandas as pd


def compute_consumption(readings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Berechnet den Verbrauch zwischen aufeinanderfolgenden Zählerständen.

    Erwartet ein DataFrame mit den Spalten:
        - reading_date (date)
        - value (float)

    Gibt ein DataFrame zurück mit zusätzlichen Spalten:
        - prev_date
        - prev_value
        - consumption      (Verbrauch in Einheiten)
        - days             (Tage zwischen den Ablesungen)
        - daily_avg        (Durchschnitt pro Tag)
    """
    if readings_df.empty:
        return readings_df

    df = readings_df.sort_values("reading_date").copy()
    df["prev_value"] = df["value"].shift(1)
    df["prev_date"] = df["reading_date"].shift(1)
    df["consumption"] = df["value"] - df["prev_value"]
    df["days"] = (
        pd.to_datetime(df["reading_date"]) - pd.to_datetime(df["prev_date"])
    ).dt.days
    df["daily_avg"] = df.apply(
        lambda r: r["consumption"] / r["days"] if r["days"] and r["days"] > 0 else None,
        axis=1,
    )
    return df


def m3_to_kwh(m3: float, z_zahl: float, brennwert: float) -> float:
    """
    Rechnet Gasverbrauch von m³ in kWh um.

    Formel: kWh = m³ × Z-Zahl × Brennwert (Hs)
    """
    return m3 * z_zahl * brennwert


def compute_costs(
    consumption: float,
    consumption_date: date,
    prices_df: pd.DataFrame,
    days: Optional[int] = None,
    is_gas: bool = False,
) -> dict:
    """
    Berechnet Kosten für einen Verbrauch basierend auf dem gültigen Preis.

    prices_df muss Spalten enthalten: valid_from (date), price_per_unit (float),
    base_price_per_month (float).
    Für Gas zusätzlich: brennwert (float), z_zahl (float).

    Gibt dict zurück:
        { 'price_per_unit', 'base_price', 'consumption_cost', 'total_cost',
          'kwh' (nur Gas), 'brennwert', 'z_zahl' }
    """
    empty = {
        "price_per_unit": None,
        "base_price": None,
        "consumption_cost": None,
        "total_cost": None,
        "kwh": None,
        "brennwert": None,
        "z_zahl": None,
    }
    if prices_df.empty:
        return empty

    df = prices_df.sort_values("valid_from")
    valid = df[df["valid_from"] <= consumption_date]
    if valid.empty:
        valid = df.head(1)

    row = valid.iloc[-1]
    price_per_unit = row["price_per_unit"]
    base_per_month = row["base_price_per_month"]

    kwh = None
    brennwert_val = None
    z_zahl_val = None

    if is_gas:
        brennwert_val = row.get("brennwert") if "brennwert" in row.index else None
        z_zahl_val = row.get("z_zahl") if "z_zahl" in row.index else None
        if brennwert_val and z_zahl_val:
            kwh = m3_to_kwh(consumption, z_zahl_val, brennwert_val)
            # Preis ist in €/kWh, Verbrauch jetzt in kWh
            consumption_cost = kwh * price_per_unit
        else:
            # Fallback: Verbrauch direkt in m³ × Preis
            consumption_cost = consumption * price_per_unit
    else:
        consumption_cost = consumption * price_per_unit

    base_cost = (base_per_month * days / 30.0) if days else 0.0
    total_cost = consumption_cost + base_cost

    return {
        "price_per_unit": price_per_unit,
        "base_price": round(base_cost, 2),
        "consumption_cost": round(consumption_cost, 2),
        "total_cost": round(total_cost, 2),
        "kwh": round(kwh, 2) if kwh is not None else None,
        "brennwert": brennwert_val,
        "z_zahl": z_zahl_val,
    }


def interpolate_daily(readings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Erstellt eine tägliche Zeitreihe durch lineare Interpolation zwischen Ablesungen.

    Erwartet Spalten: reading_date, value.

    Gibt ein DataFrame zurück mit:
        - date                (datetime, jeden Tag)
        - value               (interpolierter Zählerstand)
        - daily_consumption   (Verbrauch dieses Tages, = konstant innerhalb einer Periode)
    """
    if readings_df.empty or len(readings_df) < 2:
        return pd.DataFrame(columns=["date", "value", "daily_consumption"])

    df = readings_df.copy()
    df["reading_date"] = pd.to_datetime(df["reading_date"])
    df = df.sort_values("reading_date").drop_duplicates("reading_date")
    df = df.set_index("reading_date")[["value"]]

    # Tägliche Zeitreihe aufspannen und linear interpolieren
    daily_index = pd.date_range(df.index.min(), df.index.max(), freq="D")
    daily = df.reindex(daily_index)
    daily["value"] = daily["value"].interpolate(method="time")

    daily = daily.reset_index().rename(columns={"index": "date"})
    daily["daily_consumption"] = daily["value"].diff().clip(lower=0)
    return daily


def resample_daily(daily_df: pd.DataFrame, freq: str = "ME") -> pd.DataFrame:
    """
    Aggregiert eine tägliche Zeitreihe (aus interpolate_daily) nach Zeitraum.

    Vorteil gegenüber resample_consumption: jeder Tag ist gleichwertig gewichtet,
    unabhängig von der Unregelmäßigkeit der Ablesungen.

    freq: 'ME' = Monat, 'QE' = Quartal, 'YE' = Jahr
    """
    if daily_df.empty:
        return pd.DataFrame(columns=["period", "consumption"])

    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    resampled = df["daily_consumption"].resample(freq).sum().reset_index()
    resampled.columns = ["period", "consumption"]
    return resampled


def rolling_daily_avg(daily_df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """
    Berechnet einen gleitenden Durchschnitt des täglichen Verbrauchs.

    window: Fenstergröße in Tagen (z.B. 7, 30, 90)
    Gibt Spalten zurück: date, daily_consumption, rolling_avg
    """
    if daily_df.empty:
        return daily_df

    df = daily_df.copy()
    df["rolling_avg"] = (
        df["daily_consumption"]
        .rolling(window=window, center=True, min_periods=max(1, window // 4))
        .mean()
    )
    return df


def resample_consumption(consumption_df: pd.DataFrame, freq: str = "ME") -> pd.DataFrame:
    """
    Aggregiert Verbrauchsdaten nach Zeitraum (Perioden-basiert, Legacy).

    Für neue Plots bevorzuge resample_daily() auf Basis von interpolate_daily().
    """
    if consumption_df.empty or "consumption" not in consumption_df.columns:
        return pd.DataFrame()

    df = consumption_df.dropna(subset=["consumption"]).copy()
    df["reading_date"] = pd.to_datetime(df["reading_date"])
    df = df.set_index("reading_date")
    resampled = df["consumption"].resample(freq).sum().reset_index()
    resampled.columns = ["period", "consumption"]
    return resampled
