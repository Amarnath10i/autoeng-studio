"""Component graph and output channels for the turbocharged-engine vertical (spec §5, §6).

Channels are the named physical quantities the simulation produces per rpm point.
Components declare which channels load them, what they connect to, and their
relevant failure modes, so the what-if engine can map a changed quantity to the
parts it affects.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Channel:
    id: str
    label: str
    unit: str
    description: str
    digits: int = 1


CHANNELS: dict[str, Channel] = {
    c.id: c
    for c in [
        Channel("rpm", "Engine speed", "rpm", "Crankshaft speed.", 0),
        Channel("ve", "Volumetric efficiency", "-", "Cylinder filling vs. intake-manifold density.", 3),
        Channel("boost", "Boost", "bar", "Intake manifold gauge pressure actually achieved.", 2),
        Channel("manifold_pressure", "Manifold pressure", "kPa", "Absolute intake manifold pressure.", 1),
        Channel("pressure_ratio", "Compressor pressure ratio", "-", "Compressor outlet ÷ inlet total pressure.", 2),
        Channel("compressor_outlet_temp", "Compressor outlet temp.", "°C", "Air temperature leaving the compressor.", 0),
        Channel("charge_temp", "Charge air temp.", "°C", "Intake temperature after the intercooler.", 0),
        Channel("air_flow", "Air mass flow", "g/s", "Engine air consumption.", 1),
        Channel("corrected_air_flow", "Corrected air flow", "kg/s",
                "Compressor flow corrected to 298.15 K / 101.325 kPa. Check your map's reference conditions.", 3),
        Channel("compressor_power", "Compressor power", "kW", "Shaft power absorbed by the compressor.", 1),
        Channel("drive_power", "Supercharger drive power", "kW", "Crank power taken to drive a supercharger (zero for turbo or NA).", 1),
        Channel("turbine_power", "Turbine power", "kW", "Shaft power delivered by the turbine.", 1),
        Channel("exhaust_manifold_pressure", "Exhaust manifold pressure", "kPa", "Absolute turbine inlet pressure.", 1),
        Channel("egt", "Turbine inlet temp.", "°C", "Exhaust gas temperature at the turbine inlet.", 0),
        Channel("wastegate_fraction", "Wastegate flow share", "-", "Share of exhaust bypassing the turbine.", 2),
        Channel("boost_limited", "Turbine-limited", "-", "1 where the turbine cannot reach target boost.", 0),
        Channel("fuel_flow", "Fuel mass flow", "g/s", "Fuel consumption.", 2),
        Channel("injector_duty", "Injector duty", "-", "Required fuel flow ÷ injector static capacity.", 2),
        Channel("imep", "Gross IMEP", "bar", "Gross indicated mean effective pressure.", 2),
        Channel("pmep", "Gas-exchange MEP", "bar", "Intake minus exhaust manifold pressure (positive = gain).", 2),
        Channel("fmep", "Friction MEP", "bar", "Friction mean effective pressure.", 2),
        Channel("bmep", "BMEP", "bar", "Brake mean effective pressure.", 2),
        Channel("torque", "Brake torque", "N·m", "Crankshaft torque.", 1),
        Channel("power", "Brake power", "kW", "Crankshaft power.", 1),
        Channel("bsfc", "BSFC", "g/kWh", "Brake-specific fuel consumption.", 0),
        Channel("brake_efficiency", "Brake thermal efficiency", "-", "Brake power ÷ fuel chemical power.", 3),
        Channel("peak_pressure", "Peak cylinder pressure", "bar", "Estimated peak firing pressure (absolute).", 1),
        Channel("heat_released", "Fuel heat release", "kW", "Chemical energy released by combustion.", 1),
        Channel("heat_to_coolant", "Heat to coolant", "kW", "Heat the cooling system must reject.", 1),
        Channel("exhaust_heat", "Exhaust heat", "kW", "Sensible heat carried by exhaust gas.", 1),
        Channel("piston_speed", "Mean piston speed", "m/s", "2 × stroke × rpm / 60.", 1),
        Channel("rod_compressive_stress", "Rod compressive stress", "MPa", "Firing-TDC gas load minus inertia, on the beam section.", 1),
        Channel("rod_tensile_stress", "Rod tensile stress", "MPa", "Inertia load at exhaust TDC, on the beam section.", 1),
    ]
}


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    system: str
    channels: tuple[str, ...]
    failure_modes: tuple[str, ...]
    beginner: str
    materials_param: str | None = None
    params: tuple[str, ...] = field(default_factory=tuple)


COMPONENTS: dict[str, Component] = {
    c.id: c
    for c in [
        Component("air_intake", "Air intake", "Induction", ("corrected_air_flow",), ("filter restriction",),
                  "Draws outside air into the turbo.", params=("ambient.",)),
        Component("compressor", "Compressor (turbo / supercharger)", "Induction",
                  ("pressure_ratio", "compressor_outlet_temp", "corrected_air_flow", "compressor_power", "drive_power"),
                  ("surge", "choke", "overspeed", "bearing failure"),
                  "Spins to squeeze more air into the engine.", params=("turbo.boost_target", "turbo.compressor_efficiency")),
        Component("intercooler", "Intercooler", "Induction", ("charge_temp",), ("core leak", "heat soak"),
                  "Cools the air after the turbo heats it up.", params=("intercooler.",)),
        Component("intake_manifold", "Intake manifold", "Induction", ("manifold_pressure", "boost", "ve"),
                  ("over-pressure",), "Distributes air to each cylinder.", params=("breathing.",)),
        Component("fuel_system", "Fuel system", "Fuel", ("fuel_flow", "injector_duty"),
                  ("injector saturation", "pump flow limit"), "Delivers fuel to the cylinders.", params=("fuel.",)),
        Component("combustion_chamber", "Cylinders & pistons", "Engine core",
                  ("peak_pressure", "imep", "heat_released"),
                  ("knock (not modelled)", "piston crown failure", "head-gasket failure", "ring-land fracture"),
                  "Where fuel burns and pushes the pistons down.", params=("engine.compression_ratio", "combustion.")),
        Component("connecting_rods", "Connecting rods", "Engine core",
                  ("rod_compressive_stress", "rod_tensile_stress"),
                  ("buckling", "tensile yield", "fatigue"),
                  "Link each piston to the crankshaft.", materials_param="conrod.material_id", params=("conrod.",)),
        Component("crankshaft", "Crankshaft", "Engine core", ("torque", "piston_speed", "fmep"),
                  ("torsional fatigue", "bearing failure"),
                  "Turns the pistons' up-and-down motion into rotation.", params=("engine.", "friction.")),
        Component("turbine", "Turbo turbine", "Turbocharger",
                  ("egt", "exhaust_manifold_pressure", "turbine_power", "wastegate_fraction", "boost_limited"),
                  ("thermal failure", "overspeed", "wheel fatigue"),
                  "Uses exhaust gas to drive the compressor.", params=("turbo.turbine_", "turbo.mechanical_efficiency")),
        Component("exhaust_system", "Exhaust system", "Exhaust", ("exhaust_heat",), ("thermal cracking",),
                  "Carries exhaust gas away.", params=("exhaust.",)),
        Component("cooling_system", "Cooling system", "Thermal", ("heat_to_coolant",), ("overheating", "boil-over"),
                  "Removes engine heat through the radiator.", params=("combustion.coolant_heat_fraction",)),
        Component("clutch", "Clutch", "Driveline", ("torque",), ("slip", "thermal glazing"),
                  "Connects the engine to the gearbox."),
        Component("gearbox", "Gearbox", "Driveline", ("torque",), ("gear tooth bending", "pitting", "bearing failure"),
                  "Multiplies torque and changes speed."),
    ]
}

# (from, to, kind): kind is air | exhaust | mechanical | thermal | fuel | shaft
EDGES: list[tuple[str, str, str]] = [
    ("air_intake", "compressor", "air"),
    ("compressor", "intercooler", "air"),
    ("intercooler", "intake_manifold", "air"),
    ("intake_manifold", "combustion_chamber", "air"),
    ("fuel_system", "combustion_chamber", "fuel"),
    ("combustion_chamber", "connecting_rods", "mechanical"),
    ("connecting_rods", "crankshaft", "mechanical"),
    ("crankshaft", "clutch", "mechanical"),
    ("clutch", "gearbox", "mechanical"),
    ("combustion_chamber", "turbine", "exhaust"),
    ("turbine", "exhaust_system", "exhaust"),
    ("turbine", "compressor", "shaft"),
    ("combustion_chamber", "cooling_system", "thermal"),
]


def components_for_channel(channel: str) -> list[str]:
    return [c.id for c in COMPONENTS.values() if channel in c.channels]
