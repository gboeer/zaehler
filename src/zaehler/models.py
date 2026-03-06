from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class MeterType(str, PyEnum):
    STROM = "Strom"
    GAS = "Gas"
    WASSER = "Wasser"


class Meter(Base):
    """Zähler (Strom, Gas, Wasser)"""

    __tablename__ = "meters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    meter_type = Column(Enum(MeterType), nullable=False)
    meter_number = Column(String(100), nullable=True)
    unit = Column(String(20), nullable=False)  # kWh, m³, etc.
    location = Column(String(200), nullable=True)
    active = Column(Integer, default=1)  # 1 = aktiv, 0 = inaktiv
    created_at = Column(DateTime, default=func.now())

    readings = relationship("Reading", back_populates="meter", cascade="all, delete-orphan")
    prices = relationship("Price", back_populates="meter", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Meter {self.name} ({self.meter_type})>"


class Reading(Base):
    """Zählerstand"""

    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(Integer, ForeignKey("meters.id"), nullable=False)
    reading_date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    meter = relationship("Meter", back_populates="readings")

    def __repr__(self):
        return f"<Reading {self.reading_date}: {self.value}>"


class Price(Base):
    """Preis pro Einheit (gültig ab einem Datum)"""

    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(Integer, ForeignKey("meters.id"), nullable=False)
    valid_from = Column(Date, nullable=False)
    price_per_unit = Column(Float, nullable=False)   # €/kWh, €/m³
    base_price_per_month = Column(Float, default=0.0)  # Grundgebühr €/Monat
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    meter = relationship("Meter", back_populates="prices")

    def __repr__(self):
        return f"<Price {self.valid_from}: {self.price_per_unit}>"
