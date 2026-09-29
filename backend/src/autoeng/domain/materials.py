"""Material library (spec §7).

Materials are independent of components (spec §39.12): a component references a
material id, and any material can be swapped in. Library values are typical
handbook figures for one named condition; real properties depend on heat
treatment, section size, temperature and supplier. Properties we do not have a
reliable figure for are left out rather than guessed; the analysis then reports
"no data" for checks that need them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoeng.core.params import P, Param, Source

MATWEB_NOTE = "Typical handbook value for this condition (e.g. MatWeb / ASM); verify against your supplier's certificate"

# Property keys and units. Kept as a table so the UI and validation share one list.
PROPERTY_UNITS: dict[str, tuple[str, str]] = {
    "density": ("Density", "kg/m³"),
    "youngs_modulus": ("Young's modulus", "GPa"),
    "poisson_ratio": ("Poisson ratio", "-"),
    "yield_strength": ("Yield strength (0.2 %)", "MPa"),
    "ultimate_strength": ("Ultimate tensile strength", "MPa"),
    "fatigue_strength": ("Fatigue strength (unnotched, see ref for cycles)", "MPa"),
    "thermal_conductivity": ("Thermal conductivity", "W/(m·K)"),
    "specific_heat": ("Specific heat capacity", "J/(kg·K)"),
    "cte": ("Coefficient of thermal expansion", "µm/(m·K)"),
    "max_service_temp": ("Max service temperature", "°C"),
    "solidus_temp": ("Solidus (melting onset)", "°C"),
}


class Material(BaseModel):
    id: str
    name: str
    category: str
    condition: str = ""
    properties: dict[str, Param] = Field(default_factory=dict)
    processes: list[str] = Field(default_factory=list)
    notes: str = ""
    custom: bool = False

    def prop(self, key: str) -> Param | None:
        return self.properties.get(key)


def _lit(value: float, tol: float, ref: str = MATWEB_NOTE) -> Param:
    return P(value, Source.LITERATURE, tol, ref)


LIBRARY: dict[str, Material] = {
    m.id: m
    for m in [
        Material(
            id="aisi_4340_normalized",
            name="AISI 4340 steel",
            category="Steel",
            condition="Normalized",
            properties={
                "density": _lit(7850, 20),
                "youngs_modulus": _lit(205, 5),
                "poisson_ratio": _lit(0.29, 0.01),
                "yield_strength": _lit(710, 50),
                "ultimate_strength": _lit(1110, 60),
                "thermal_conductivity": _lit(44.5, 3),
                "specific_heat": _lit(475, 15),
                "cte": _lit(12.3, 0.5),
                "solidus_temp": _lit(1427, 20),
            },
            processes=["forging", "CNC machining"],
            notes="Quenched-and-tempered 4340 is much stronger; add it as a custom material with certificate data.",
        ),
        Material(
            id="ti_6al_4v_annealed",
            name="Ti-6Al-4V (Grade 5)",
            category="Titanium",
            condition="Annealed",
            properties={
                "density": _lit(4430, 20),
                "youngs_modulus": _lit(113.8, 3),
                "poisson_ratio": _lit(0.342, 0.01),
                "yield_strength": _lit(880, 40),
                "ultimate_strength": _lit(950, 40),
                "fatigue_strength": _lit(510, 60, MATWEB_NOTE + "; unnotched, 1e7 cycles"),
                "thermal_conductivity": _lit(6.7, 0.5),
                "specific_heat": _lit(526, 15),
                "cte": _lit(8.6, 0.4),
                "solidus_temp": _lit(1604, 20),
            },
            processes=["forging", "CNC machining", "additive manufacturing"],
        ),
        Material(
            id="al_7075_t6",
            name="Aluminium 7075",
            category="Aluminium",
            condition="T6",
            properties={
                "density": _lit(2810, 10),
                "youngs_modulus": _lit(71.7, 1.5),
                "poisson_ratio": _lit(0.33, 0.01),
                "yield_strength": _lit(503, 25),
                "ultimate_strength": _lit(572, 25),
                "fatigue_strength": _lit(159, 20, MATWEB_NOTE + "; 5e8 cycles, R.R. Moore"),
                "thermal_conductivity": _lit(130, 5),
                "specific_heat": _lit(960, 30),
                "cte": _lit(23.6, 0.5),
                "solidus_temp": _lit(477, 5),
            },
            processes=["forging", "CNC machining"],
            notes="Strength drops markedly above ~100 °C; temperature effects are not modelled yet.",
        ),
        Material(
            id="al_2618_t61",
            name="Aluminium 2618",
            category="Aluminium",
            condition="T61",
            properties={
                "density": _lit(2760, 10),
                "youngs_modulus": _lit(74.5, 2),
                "poisson_ratio": _lit(0.33, 0.01),
                "yield_strength": _lit(372, 25),
                "ultimate_strength": _lit(441, 25),
                "thermal_conductivity": _lit(146, 6),
                "specific_heat": _lit(875, 30),
                "cte": _lit(22.3, 0.5),
            },
            processes=["forging", "CNC machining"],
            notes="Common forged-piston alloy. Fatigue data not in library: add it from a supplier to enable fatigue checks.",
        ),
        Material(
            id="grey_cast_iron",
            name="Grey cast iron",
            category="Cast iron",
            condition="Brake-disc grade (typical)",
            properties={
                "density": _lit(7200, 100),
                "youngs_modulus": _lit(110, 20),
                "ultimate_strength": _lit(220, 40),
                "thermal_conductivity": _lit(50, 10),
                "specific_heat": _lit(460, 30, MATWEB_NOTE + "; room temperature, rises with temperature"),
                "cte": _lit(11.0, 1.0),
                "solidus_temp": _lit(1150, 50),
            },
            processes=["casting", "CNC machining"],
            notes="Brittle: no yield strength is defined. Properties vary strongly with graphite form and carbon content.",
        ),
        Material(
            id="steel_dc04",
            name="Mild steel sheet DC04",
            category="Steel",
            condition="Cold-rolled deep-drawing sheet (EN 10130)",
            properties={
                "density": _lit(7850, 20),
                "youngs_modulus": _lit(210, 5),
                "yield_strength": _lit(175, 35, "EN 10130 range 140-210 MPa"),
                "ultimate_strength": _lit(310, 40, "EN 10130 range 270-350 MPa"),
            },
            processes=["sheet-metal forming", "spot welding"],
            notes="Typical outer-panel steel. Coated and bake-hardening grades differ.",
        ),
        Material(
            id="al_6016_t4",
            name="Aluminium 6016",
            category="Aluminium",
            condition="T4 automotive body sheet",
            properties={
                "density": _lit(2700, 10),
                "youngs_modulus": _lit(70, 2),
                "yield_strength": _lit(120, 20),
                "ultimate_strength": _lit(230, 25),
            },
            processes=["sheet-metal forming", "riveting", "adhesive bonding"],
            notes="Outer-panel alloy; strength rises after paint-bake.",
        ),
    ]
}
