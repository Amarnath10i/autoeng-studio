"""Turbocharged engine design: the data a user edits, versions and simulates.

The Pydantic models define the stored shape. `PARAM_SPECS` is the single source of
truth for each parameter's unit, allowed range and explanations; it drives
validation, the UI forms and education mode.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from autoeng.core.params import Param, ParamSpec
from autoeng.domain.fuels import FUELS

SCHEMA_VERSION = 1


def _spec(path, label, unit, lo, hi, beginner, engineer, **kw) -> ParamSpec:
    return ParamSpec(path, label, unit, lo, hi, path.split(".")[0], beginner, engineer, **kw)


LAYOUT_CHOICES = (("inline", "Inline"), ("v", "V"), ("w", "W"), ("flat", "Flat (boxer)"))
CRANK_CHOICES = (("standard", "Standard"), ("cross_plane", "Cross-plane (V8)"), ("flat_plane", "Flat-plane (V8)"))
INDUCTION_CHOICES = (
    ("turbo", "Turbocharged"),
    ("naturally_aspirated", "Naturally aspirated"),
    ("supercharger_pd", "Supercharged: positive displacement (roots / screw)"),
    ("supercharger_centrifugal", "Supercharged: centrifugal"),
)

PARAM_SPECS: dict[str, ParamSpec] = {
    s.path: s
    for s in [
        # --- Architecture
        _spec("architecture.layout", "Cylinder layout", "-", 0, 0,
              "How the cylinders are arranged: in a line, in a V, in a W or flat and opposed.",
              "Sets cylinder positions and bank angles: drives balance, firing intervals and package size.",
              kind="choice", choices=LAYOUT_CHOICES),
        _spec("architecture.bank_angle", "Bank angle", "deg", 10, 180,
              "The angle between the two rows of cylinders in a V or W engine.",
              "Included angle between banks (V and W). Even firing for a V needs 720°/n multiples; 90° suits V8, 60° suits V6/V12.",
              step=1),
        _spec("architecture.crank", "Crankshaft", "-", 0, 0,
              "How the crank pins are arranged (matters most for V8s).",
              "Cross-plane V8: pins at 90° (smooth, secondary balanced). Flat-plane: pins at 180° (light, free secondary force).",
              kind="choice", choices=CRANK_CHOICES),
        _spec("architecture.induction", "Induction", "-", 0, 0,
              "How air is pushed into the engine: naturally, by an exhaust turbo, or a belt-driven supercharger.",
              "Turbo: exhaust-driven with wastegate. Positive-displacement supercharger: near-constant boost, crank-driven. "
              "Centrifugal: boost rises with rpm². Naturally aspirated: no boost device.",
              kind="choice", choices=INDUCTION_CHOICES),
        _spec("architecture.supercharger_drive_efficiency", "Supercharger drive efficiency", "-", 0.5, 1.0,
              "How much crank power the supercharger belt and gears waste.",
              "Belt/gear drive efficiency; crank power taken = compressor power ÷ this. Used only for superchargers.",
              step=0.01),
        # --- Engine geometry
        _spec("engine.cylinders", "Cylinders", "-", 1, 16,
              "How many cylinders the engine has.",
              "Number of cylinders; total displacement scales linearly.",
              integer=True, kind="int"),
        _spec("engine.bore", "Bore", "mm", 40, 160,
              "The diameter of each cylinder.",
              "Cylinder bore B. Piston area = πB²/4 sets the gas force on the piston.", step=0.1),
        _spec("engine.stroke", "Stroke", "mm", 40, 160,
              "How far each piston travels from top to bottom.",
              "Stroke S = 2 × crank radius. Sets displacement and mean piston speed 2SN.", step=0.1),
        _spec("engine.rod_length", "Connecting rod length", "mm", 80, 300,
              "The length of the rod joining piston and crankshaft.",
              "Centre-to-centre length L. Sets rod ratio r/L for piston kinematics and the rod's buckling length.", step=0.1),
        _spec("engine.compression_ratio", "Compression ratio", "-", 6, 16,
              "How much the air-fuel mixture is squeezed before it burns.",
              "Geometric CR = (Vd + Vc)/Vc. Raises ideal Otto efficiency 1 − CR^(1−γ) and compression pressure.", step=0.1),
        # --- Operating range
        _spec("operating.rpm_min", "Sweep start", "rpm", 500, 10000,
              "Lowest engine speed on the virtual dyno.", "Start of the full-load rpm sweep.",
              integer=True, kind="int"),
        _spec("operating.rpm_max", "Redline", "rpm", 1000, 20000,
              "The highest engine speed the engine is allowed to run.",
              "End of the full-load sweep; also the base for the overspeed load case.",
              integer=True, kind="int"),
        _spec("operating.rpm_step", "Sweep step", "rpm", 50, 1000,
              "Spacing between dyno points.", "Resolution of the rpm sweep.",
              integer=True, kind="int"),
        # --- Breathing
        _spec("breathing.ve_peak", "Peak volumetric efficiency", "-", 0.5, 1.3,
              "How well the engine fills its cylinders with air at its best speed.",
              "Peak VE referenced to intake-manifold density. Set by cam timing, ports and runner tuning.", step=0.01),
        _spec("breathing.ve_peak_rpm", "Rpm of peak VE", "rpm", 1000, 15000,
              "The engine speed where the engine breathes best.",
              "Rpm of peak VE (tuned intake/cam).", step=50),
        _spec("breathing.ve_falloff", "VE falloff", "-", 0.0, 1.0,
              "How much breathing worsens away from that best speed.",
              "VE(N) = VE_pk − k·((N − N_pk)/(N_max − N_min))². Level-1 shape; replace with a measured VE map when available.",
              step=0.01),
        # --- Turbocharger
        _spec("turbo.boost_target", "Target boost", "bar (gauge)", 0.0, 4.0,
              "How much extra pressure the turbo is asked to push into the engine.",
              "Manifold gauge pressure the wastegate controller targets. Actual boost is lower where the turbine cannot supply enough power.",
              step=0.01),
        _spec("turbo.compressor_efficiency", "Compressor efficiency", "-", 0.4, 0.85,
              "How efficiently the turbo compresses air; lower means hotter air.",
              "Total-to-total isentropic efficiency, held constant here (Level 1). Read it off the compressor map at the operating point.",
              step=0.01),
        _spec("turbo.turbine_efficiency", "Turbine efficiency", "-", 0.4, 0.85,
              "How well the turbine turns exhaust energy into spin.",
              "Total-to-static isentropic efficiency of the turbine, constant (Level 1).", step=0.01),
        _spec("turbo.mechanical_efficiency", "Turbo shaft efficiency", "-", 0.8, 1.0,
              "Friction losses in the turbo's bearings.",
              "Bearing/shaft mechanical efficiency linking turbine and compressor power.", step=0.01),
        _spec("turbo.turbine_flow_area", "Turbine effective flow area", "cm²", 1.0, 30.0,
              "Smaller turbines spool faster but choke the engine at high rpm.",
              "Effective nozzle area of the turbine (set by housing A/R and wheel). Governs exhaust back-pressure and spool.",
              step=0.1),
        # --- Intercooler
        _spec("intercooler.effectiveness", "Intercooler effectiveness", "-", 0.0, 1.0,
              "How much of the turbo's heat the intercooler removes.",
              "ε = (T_in − T_out)/(T_in − T_ambient), air-to-air.", step=0.01),
        _spec("intercooler.pressure_drop", "Intercooler pressure drop", "bar", 0.0, 0.5,
              "Boost lost pushing air through the intercooler.",
              "Charge-air pressure drop; the compressor must make this up. Held constant (Level 1).", step=0.01),
        # --- Combustion
        _spec("combustion.lambda_ratio", "Lambda (full load)", "-", 0.6, 1.5,
              "How rich the fuel mixture is. Below 1 means extra fuel to keep things cool.",
              "λ = AFR/AFR_stoich. For λ < 1 only the air-limited share of fuel releases heat.", step=0.01),
        _spec("combustion.efficiency_ratio", "Efficiency vs. ideal cycle", "-", 0.4, 0.95,
              "How close the real engine gets to the theoretical best.",
              "Gross indicated efficiency ÷ ideal Otto efficiency (γ below). Lumps heat loss, finite burn duration and knock-limited spark retard.",
              step=0.01),
        _spec("combustion.cycle_gamma", "Cycle γ", "-", 1.2, 1.4,
              "A property of hot gases used in the efficiency formula.",
              "Effective ratio of specific heats for the ideal-cycle efficiency; ~1.3 represents burned-gas properties.",
              step=0.005),
        _spec("combustion.combustion_efficiency", "Combustion efficiency", "-", 0.8, 1.0,
              "How much of the fuel actually burns.", "Fraction of available chemical energy released.", step=0.005),
        _spec("combustion.pressure_rise_ratio", "Combustion pressure rise", "-", 1.5, 5.0,
              "How sharply pressure jumps when the mixture burns.",
              "Peak ÷ end-of-compression pressure. Used for the Level-1 peak cylinder pressure estimate.", step=0.05),
        _spec("combustion.polytropic_n", "Compression polytropic index", "-", 1.2, 1.4,
              "Describes how gas heats up as it is squeezed.",
              "n in pV^n = const during compression.", step=0.005),
        _spec("combustion.coolant_heat_fraction", "Heat to coolant", "-", 0.05, 0.5,
              "Share of the fuel's energy that ends up in the cooling system.",
              "Fraction of released fuel energy rejected to coolant (and oil). Drives the cooling-system load.", step=0.01),
        # --- Exhaust
        _spec("exhaust.backpressure", "Post-turbine back-pressure", "bar (gauge)", 0.0, 1.0,
              "Restriction of the exhaust pipes and catalyst after the turbo.",
              "Turbine outlet gauge pressure (downpipe, catalyst, silencers), held constant (Level 1).", step=0.01),
        _spec("exhaust.gas_cp", "Exhaust gas cp", "J/(kg·K)", 1000, 1350,
              "How much energy hot exhaust gas stores per degree.",
              "Mean specific heat of exhaust gas across the turbine.", step=5),
        _spec("exhaust.gas_gamma", "Exhaust gas γ", "-", 1.25, 1.4,
              "A property of hot exhaust gas.", "Ratio of specific heats for turbine expansion and nozzle flow.", step=0.005),
        # --- Friction
        _spec("friction.a", "Friction constant term", "bar", 0.0, 3.0,
              "Friction losses that exist at any speed.",
              "FMEP = a + b·(N/1000) + c·(N/1000)². Correlation form of Barnes-Moss (Heywood 1988, ch. 13).", step=0.01),
        _spec("friction.b", "Friction linear term", "bar/krpm", 0.0, 1.0,
              "Friction that grows with engine speed.", "Linear coefficient of the FMEP correlation.", step=0.005),
        _spec("friction.c", "Friction quadratic term", "bar/krpm²", 0.0, 0.3,
              "Friction that grows fast at high speed.", "Quadratic coefficient of the FMEP correlation.", step=0.005),
        # --- Fuel system
        _spec("fuel.fuel_id", "Fuel", "-", 0, 0,
              "The fuel the engine burns.", "Sets LHV, stoichiometric AFR and density.",
              kind="choice", choices_from="fuels"),
        _spec("fuel.injector_flow", "Injector static flow", "cc/min", 50, 3000,
              "How much fuel each injector can deliver.",
              "Static flow per injector at its rated fuel pressure.", step=5),
        _spec("fuel.injector_count", "Injectors", "-", 1, 32,
              "How many fuel injectors there are.", "Total injector count.", integer=True, kind="int"),
        # --- Ambient
        _spec("ambient.temperature", "Ambient temperature", "°C", -40, 60,
              "Outside air temperature.", "Compressor inlet and intercooler sink temperature.", step=0.5),
        _spec("ambient.pressure", "Ambient pressure", "kPa", 50, 110,
              "Outside air pressure (lower at altitude).", "Compressor inlet static pressure.", step=0.1),
        # --- Connecting rod
        _spec("conrod.material_id", "Rod material", "-", 0, 0,
              "What the connecting rods are made of.", "Material used for rod stress, buckling and fatigue checks.",
              kind="choice", choices_from="materials"),
        _spec("conrod.section_height", "Beam section height", "mm", 5, 60,
              "Depth of the rod's I-beam (in the direction the crank swings).",
              "I-section depth H, measured in the plane of rotation, at the minimum section.", step=0.1),
        _spec("conrod.section_width", "Beam flange width", "mm", 5, 60,
              "Width of the rod's I-beam.", "I-section flange width W.", step=0.1),
        _spec("conrod.flange_thickness", "Flange thickness", "mm", 1, 20,
              "Thickness of the rod's I-beam flanges.", "Flange thickness t_f.", step=0.1),
        _spec("conrod.web_thickness", "Web thickness", "mm", 1, 20,
              "Thickness of the rod's I-beam middle wall.", "Web thickness t_w.", step=0.1),
        _spec("conrod.volume", "Rod volume", "cm³", 10, 500,
              "Size of one rod; with material density it gives the rod's mass.",
              "Solid volume of one rod (from CAD). Mass = ρ·V, so material swaps change inertia loads.", step=0.5),
        _spec("conrod.piston_group_mass", "Piston group mass", "g", 100, 2000,
              "Weight of the piston, pin and rings.",
              "Piston + pin + rings + clips: the reciprocating mass excluding the rod.", step=1),
        _spec("conrod.small_end_fraction", "Rod mass at small end", "-", 0.1, 0.5,
              "How much of the rod's weight moves up and down with the piston.",
              "Share of rod mass lumped at the small end (two-mass dynamic equivalence); weigh it on a scale to measure.",
              step=0.01),
        _spec("conrod.fatigue_factor", "Fatigue modification factor", "-", 0.1, 1.0,
              "How much real-world surface finish and size reduce fatigue strength.",
              "Product of Marin factors (surface, size, reliability, ...) applied to the material fatigue strength.", step=0.01),
        _spec("conrod.overspeed_factor", "Overspeed load case", "× redline", 1.0, 1.5,
              "Checks the rods if the engine is over-revved (e.g. a missed shift).",
              "Tensile inertia load case evaluated at this multiple of redline.", step=0.01),
        # --- Targets
        _spec("targets.peak_power", "Target peak power", "kW", 1, 3000,
              "The peak power you are aiming for.", "Design requirement on peak brake power.", optional=True, step=1),
        _spec("targets.peak_torque", "Target peak torque", "N·m", 1, 5000,
              "The peak torque you are aiming for.", "Design requirement on peak brake torque.", optional=True, step=1),
    ]
}


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _default_param(value: float, ref: str) -> Param:
    return Param(value=value, source="estimated", tol=0.0, ref=ref)


class ArchitectureSection(_Section):
    layout: str = "inline"
    bank_angle: Param = Field(default_factory=lambda: _default_param(90.0, "Default bank angle"))
    crank: str = "standard"
    induction: str = "turbo"
    supercharger_drive_efficiency: Param = Field(
        default_factory=lambda: _default_param(0.9, "Typical belt drive efficiency (estimated)")
    )


class EngineSection(_Section):
    cylinders: int = Field(ge=1, le=16)
    bore: Param
    stroke: Param
    rod_length: Param
    compression_ratio: Param


class OperatingSection(_Section):
    rpm_min: int
    rpm_max: int
    rpm_step: int


class BreathingSection(_Section):
    ve_peak: Param
    ve_peak_rpm: Param
    ve_falloff: Param


class TurboSection(_Section):
    boost_target: Param
    compressor_efficiency: Param
    turbine_efficiency: Param
    mechanical_efficiency: Param
    turbine_flow_area: Param


class IntercoolerSection(_Section):
    effectiveness: Param
    pressure_drop: Param


class CombustionSection(_Section):
    lambda_ratio: Param
    efficiency_ratio: Param
    cycle_gamma: Param
    combustion_efficiency: Param
    pressure_rise_ratio: Param
    polytropic_n: Param
    coolant_heat_fraction: Param


class ExhaustSection(_Section):
    backpressure: Param
    gas_cp: Param
    gas_gamma: Param


class FrictionSection(_Section):
    a: Param
    b: Param
    c: Param


class FuelSection(_Section):
    fuel_id: str
    injector_flow: Param
    injector_count: int = Field(ge=1, le=32)


class AmbientSection(_Section):
    temperature: Param
    pressure: Param


class ConrodSection(_Section):
    material_id: str
    section_height: Param
    section_width: Param
    flange_thickness: Param
    web_thickness: Param
    volume: Param
    piston_group_mass: Param
    small_end_fraction: Param
    fatigue_factor: Param
    overspeed_factor: Param


class TargetsSection(_Section):
    peak_power: Param | None = None
    peak_torque: Param | None = None


class Limit(_Section):
    """An allowable maximum on one output channel of one component (spec §15)."""

    id: str
    component: str
    channel: str
    allowable: Param
    label: str | None = None


class EngineDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    architecture: ArchitectureSection = Field(default_factory=ArchitectureSection)
    engine: EngineSection
    operating: OperatingSection
    breathing: BreathingSection
    turbo: TurboSection
    intercooler: IntercoolerSection
    combustion: CombustionSection
    exhaust: ExhaustSection
    friction: FrictionSection
    fuel: FuelSection
    ambient: AmbientSection
    conrod: ConrodSection
    targets: TargetsSection = Field(default_factory=TargetsSection)
    limits: list[Limit] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ranges(self) -> EngineDesign:
        errors: list[str] = []
        for path, spec in PARAM_SPECS.items():
            value = get_path(self, path)
            if value is None:
                if not spec.optional:
                    errors.append(f"{path}: missing")
                continue
            if spec.kind == "choice":
                continue
            v = value.value if isinstance(value, Param) else value
            if not (spec.min <= v <= spec.max):
                errors.append(f"{path} = {v} {spec.unit} is outside [{spec.min}, {spec.max}]")
        op = self.operating
        if op.rpm_max <= op.rpm_min:
            errors.append("operating.rpm_max must exceed operating.rpm_min")
        elif (op.rpm_max - op.rpm_min) / op.rpm_step > 400:
            errors.append("rpm sweep has more than 400 points; increase operating.rpm_step")
        if self.fuel.fuel_id not in FUELS:
            errors.append(f"fuel.fuel_id: unknown fuel '{self.fuel.fuel_id}'")
        arch = self.architecture
        for key, choices in (("layout", LAYOUT_CHOICES), ("crank", CRANK_CHOICES), ("induction", INDUCTION_CHOICES)):
            if getattr(arch, key) not in {c for c, _ in choices}:
                errors.append(f"architecture.{key}: unknown value '{getattr(arch, key)}'")
        from autoeng.physics.balance import validate_layout

        layout_error = validate_layout(arch.layout, self.engine.cylinders)
        if layout_error:
            errors.append(f"architecture.layout: {layout_error}")
        if arch.crank != "standard" and not (arch.layout == "v" and self.engine.cylinders == 8):
            errors.append("architecture.crank: flat-plane and cross-plane cranks apply to V8 engines only")
        c = self.conrod
        if 2 * c.flange_thickness.value >= c.section_height.value:
            errors.append("conrod: 2 × flange thickness must be less than section height")
        if c.web_thickness.value > c.section_width.value:
            errors.append("conrod: web thickness cannot exceed flange width")
        if self.engine.rod_length.value <= self.engine.stroke.value / 2:
            errors.append("engine.rod_length must exceed the crank radius (stroke / 2)")
        ids = [lim.id for lim in self.limits]
        if len(ids) != len(set(ids)):
            errors.append("limits: ids must be unique")
        if errors:
            raise ValueError("; ".join(errors))
        return self


def get_path(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
        if obj is None:
            return None
    return obj
