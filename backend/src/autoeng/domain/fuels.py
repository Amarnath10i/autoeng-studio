"""Fuel property catalog.

Values are typical literature figures. Real pump fuels vary by blend, season and
region, which is why each property carries a tolerance rather than a single number.
"""

from __future__ import annotations

from pydantic import BaseModel

from autoeng.core.params import P, Param, Source

HEYWOOD = "Heywood, Internal Combustion Engine Fundamentals (1988), App. D"


class Fuel(BaseModel):
    id: str
    name: str
    lhv: Param  # lower heating value, MJ/kg
    afr_stoich: Param  # stoichiometric air/fuel ratio by mass, -
    density: Param  # liquid density, kg/L
    notes: str = ""


FUELS: dict[str, Fuel] = {
    f.id: f
    for f in [
        Fuel(
            id="gasoline_e0",
            name="Gasoline (no ethanol)",
            lhv=P(43.4, Source.LITERATURE, 0.6, HEYWOOD),
            afr_stoich=P(14.6, Source.LITERATURE, 0.1, HEYWOOD),
            density=P(0.745, Source.LITERATURE, 0.02, "Typical pump gasoline range 0.72-0.775 kg/L"),
            notes="Composition varies by refinery and season.",
        ),
        Fuel(
            id="gasoline_e10",
            name="Gasoline E10",
            lhv=P(41.9, Source.LITERATURE, 0.7, "Blend of gasoline and 10 % v/v ethanol"),
            afr_stoich=P(14.1, Source.LITERATURE, 0.1, "Blend of gasoline and 10 % v/v ethanol"),
            density=P(0.75, Source.LITERATURE, 0.02, "Typical pump fuel range"),
        ),
        Fuel(
            id="e85",
            name="E85 (flex fuel)",
            lhv=P(29.2, Source.LITERATURE, 1.5, "Ethanol content varies ~51-83 % v/v by season"),
            afr_stoich=P(9.8, Source.LITERATURE, 0.4, "Ethanol content varies ~51-83 % v/v by season"),
            density=P(0.781, Source.LITERATURE, 0.01, "Blend-dependent"),
            notes="Ethanol content varies seasonally; measure it (flex-fuel sensor) for real tuning.",
        ),
        Fuel(
            id="ethanol",
            name="Ethanol (E100)",
            lhv=P(26.9, Source.LITERATURE, 0.3, HEYWOOD),
            afr_stoich=P(9.0, Source.LITERATURE, 0.05, HEYWOOD),
            density=P(0.789, Source.LITERATURE, 0.005, "Pure ethanol at 20 °C"),
        ),
        Fuel(
            id="methanol",
            name="Methanol (M100)",
            lhv=P(20.0, Source.LITERATURE, 0.2, HEYWOOD),
            afr_stoich=P(6.47, Source.LITERATURE, 0.05, HEYWOOD),
            density=P(0.792, Source.LITERATURE, 0.005, "Pure methanol at 20 °C"),
        ),
    ]
}
