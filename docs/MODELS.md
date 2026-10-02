# Physics model reference

Every model here is fidelity level 1–2 (analytical / reduced-order, spec §11). Each is versioned, lists its
assumptions in the result's trust block, and runs vectorised over Monte Carlo samples. Symbols use SI units internally.

## Uncertainty and provenance

Each input is a `Param(value, source, tol, dist)`. `tol` is a half-width read as an ≈95 % interval: uniform samples lie
in value ± tol; normal samples use σ = tol / 1.96. Every parameter draws from its own random stream seeded by
`(seed, parameter path)`, so two designs that share a parameter share its samples (common random numbers). What-if
comparisons therefore show the effect of the change, not sampling noise.

Result bands are the 5th–95th percentiles over samples. They include input uncertainty only; model-form error is not
quantified until a model is calibrated against measurements.

## Turbocharged SI engine: `engine.turbo_si_mvem` v1.0.0

Per rpm point N, for a boost level b (gauge):

| Quantity | Relation |
|---|---|
| Manifold pressure | p_m = p_amb + b; compressor outlet p₂ = p_m + Δp_ic; PR = p₂ / p_amb |
| Compressor outlet temperature | T₂ = T₁ · (1 + (PR^((γ−1)/γ) − 1) / η_c), γ = 1.4 |
| Charge temperature | T_m = T₂ − ε · (T₂ − T_amb) |
| Air flow | ṁ_a = VE(N) · p_m / (R T_m) · V_d · N / 120 |
| Fuel flow | ṁ_f = ṁ_a / (λ · AFR_st); burned fuel = ṁ_a / (AFR_st · max(λ, 1)) |
| Heat released | Q = η_comb · LHV · ṁ_burned |
| Gross indicated power | W_i = k_eff · (1 − CR^(1−γ_cycle)) · Q |
| Heat to coolant, exhaust | Q_c = f_c · Q; Q_x = Q − W_i − Q_c |
| Turbine inlet temperature | T₃ = T_m + Q_x / (ṁ_x c_p,x) |
| Compressor power | W_c = ṁ_a c_p (T₂ − T₁) |
| Turbine flow (nozzle) | ṁ = A · p₃ / √(R T₃) · Ψ(p₄/p₃), Ψ from isentropic nozzle flow, choked below the critical ratio |
| Turbine power | W_t = ṁ_t c_p,x T₃ η_t (1 − (p₄/p₃)^((γ_x−1)/γ_x)) |

Boost solution: if the turbine with the wastegate shut can drive the compressor at the target boost
(W_t η_m ≥ W_c), the wastegate opens until the power balance holds and p₃ follows. Otherwise boost is reduced by
bisection until W_t η_m = W_c (turbine-limited, the spool region).

Brake output: IMEP = W_i · 120 / (V_d N); PMEP = p_m − p₃; FMEP = a + b·(N/1000) + c·(N/1000)² (Barnes-Moss form,
Heywood 1988 ch. 13); BMEP = IMEP + PMEP − FMEP; torque T = BMEP · V_d / 4π; P = T ω.

Peak cylinder pressure (order-of-magnitude): p_max = p_m · CR^n · r_p.

Induction types (same model, different boost source):

| Induction | Boost | Cost |
|---|---|---|
| Turbocharged | Wastegate target, or turbine-limited (above) | Exhaust back-pressure p₃ (pumping loss) |
| Naturally aspirated | None: p_m = p_amb − Δp_intake, PR = 1, T₂ = T_amb | – |
| Positive-displacement supercharger (roots, screw) | Target boost at every rpm | Drive power W_d = W_c / η_drive taken from the crank |
| Centrifugal supercharger | b(N) = b_target · min(1, (N / N_max)²) | W_d = W_c / η_drive |

Supercharger drive power is subtracted as a mean effective pressure, BMEP = IMEP + PMEP − FMEP − W_d·120/(V_d N),
and reported as its own channel.

Not modelled: knock and spark timing, compressor maps (surge, choke, shaft speed), transients and pulse energy,
flow-dependent pressure losses, variable valve timing, exhaust gas recirculation.

## Connecting rod: `structure.conrod_beam` v1.0.0

- I-section: A = 2 W t_f + (H − 2 t_f) t_w; in-plane and out-of-plane second moments of area.
- Reciprocating mass m = m_piston + k_small-end · ρ · V_rod; inertia force at TDC F_i = m r ω² (1 + r/L).
- Firing: σ_c = (F_gas − F_i) / A with F_gas = (p_max − p_amb) π B²/4. Exhaust TDC: σ_t = F_i / A; also at the overspeed
  load case.
- Buckling: Johnson parabola below the transition slenderness √(2π²E/σ_y), Euler above; effective length L in plane,
  0.5 L out of plane.
- Fatigue: modified Goodman on the tension–compression cycle with S_e = S_f' × Marin factor (compressive mean:
  n = S_e / σ_a). Skipped with "no data" when the material has no fatigue strength.

## Engine layout, balance and firing: `structure.engine_balance` v1.0.0

Layouts: inline (1–6, 8), V (2–16, any bank angle), W (8, 12, 16 as two narrow-angle VR banks set in a V) and flat
(boxer up to 6 cylinders; 180° V with shared pins above). Each cylinder has a position along the crank x, a bank angle β
and a crankpin angle φ₀.

- Reciprocating force of one piston along its bore: F = m r ω² [cos ψ + λ cos 2ψ], ψ = θ + φ₀ − β, λ = r / L.
- Engine shaking force and rocking couple: vector sums of F and x·F over all cylinders through one revolution, split
  into first (primary) and second (secondary) order. A primary force or couple of constant magnitude that rotates with
  the crank is reported as cancellable by counterweights.
- V engines use split crankpins (offset = bank angle − 720°/n) so any bank angle fires evenly; a 90° V8 is cross-plane
  (pins 0/90/270/180) or flat-plane (two inline fours).
- Firing order: each crank throw can fire on either of its two top-dead-centres per 720° cycle; the choice is an optimal
  assignment (Hungarian algorithm) to an evenly spaced grid, which gives the textbook sequences (even for I4/I6/V8, 270/450
  for a 90° V-twin).
- Package: block length, width and height from bore spacing (1.25 B), deck height and bank angle.

Checked against textbook results: I4 secondary force 4λ·m r ω²; I6 and flat-12 fully balanced; cross-plane V8 with a
rotating primary couple only; flat-plane V8 secondary force √2 · 4λ.

## Straight-line vehicle performance: `vehicle.longitudinal` v1.0.0

- Wheel force per gear: F = T(N) · i_g · i_fd · η / r_w, with N from road speed; launch holds the engine at the launch rpm
  while the clutch slips.
- Resistance: ½ ρ C_d A v² + C_rr m g. Rotating inertia (v1.1): γ = 1 + (4 I_wheel + I_engine ξ² η) / (m r²), with ξ the overall ratio; defaults I_engine ≈ 0.10 + 0.05 V_d[L] kg·m² and I_wheel ≈ 1.1 (r / 0.32 m)² kg·m², overridable on the clutch and tyre components. (v1.0 used Wong's γ = 1.04 + 0.0025 ξ², which overstates inertia with the tall first gears of modern 7- and 8-speed gearboxes.)
- Traction: μ × driven-axle load with longitudinal weight transfer m a h / L (closed form for front and rear drive).
- Optimal upshifts with a torque-free shift time; top speed where no gear can overcome resistance.

## Time-domain duty cycle: `thermal.duty_cycle` v1.0.0

- Driver: first-order speed tracking (τ = 2 s) within powertrain, traction and braking limits; highest gear that can
  deliver the demanded force.
- Part-load fuel power (Willans line): P_fuel = (P_brake + P_friction(N)) / η_i(N) from the engine model at the scenario's
  ambient conditions.
- Coolant (lumped engine + coolant + oil): C dT/dt = f_c P_fuel − s(T) UA(v) (T − T_amb), thermostat opening s(T),
  UA ∝ airflow^n with a fan minimum.
- Front brake disc (per disc): m c dT/dt = F_brake v · bias / 2 − A [h(v)(T − T_amb) + ε σ (T⁴ − T_amb⁴)],
  h = h₀ + h₁ v^0.8.
- Weather: ISA pressure from altitude, air density, ambient temperature, headwind, surface friction factor.
- Events per sample: first time the coolant or disc limit is exceeded, and sustained inability to hold the requested
  speed.

## Limits and status bands

Safety factor = allowable ÷ load (temperatures use the rise above ambient). The status uses the nominal SF and the
conservative 5th-percentile SF:

| Status | Rule (thermal limits use 1.05 / 1.10) |
|---|---|
| Predicted failure | nominal SF < 1 |
| Critical | nominal SF < 1.10, or 5th-percentile SF < 1 |
| Warning | 5th-percentile SF < 1.25 |
| OK | otherwise |
| No data | allowable or material property unknown |

These bands are a project convention, not a certification standard.

## Calibration

Bounded nonlinear least squares (SciPy `least_squares`) on torque residuals scaled by 1 % of mean torque, plus boost
residuals scaled by 0.02 bar when boost is measured. The covariance (JᵀJ)⁻¹ s² gives 95 % intervals that become the
calibrated parameters' tolerances; parameter pairs with |ρ| > 0.95 are reported as not separately identifiable.

## Community priors

For a design, shared calibrations are weighted by w = exp(−½ Σ(Δdᵢ/sᵢ)²) over displacement (0.5 L), compression ratio
(1.0), boost (0.5 bar), bore/stroke (0.15) and cylinder count (2), × 0.3 for a different fuel. A suggestion needs an
effective sample size (Σw)²/Σw² ≥ 3; its spread combines between-engine variance and the fits' own variance.

## Detailed body surface: `geometry.body_loft` v1.0.0

The body is lofted from the sketches into a closed quad mesh (120 sections × 88 points around):

- each section is the intersection of the roofline (side profile) with the front section, scaled by a plan-view taper
  that rounds the bumper corners;
- above the beltline the glasshouse leans in by the tumblehome factor; the roof and bonnet carry a slight crown;
- the underbody sweeps up at the nose and into a rear diffuser;
- skin points inside a circle of (wheel radius + arch gap) around each wheel are pushed in to the wheel-well wall, so the
  tyre sits in a recess.

Imported STL/OBJ meshes are converted to the car frame (units, Y-up or Z-up, nose detected from the lower bonnet end,
lowest point on the road). Voxelisation casts rays along x, y and z and counts surface crossings (parity); a cell is solid
when at least two directions agree, which tolerates small holes in imported meshes.

## Virtual wind tunnel: `aero.lbm_d3q19_les` v1.0.0

- Lattice Boltzmann, D3Q19 velocity set, BGK collision with a Smagorinsky sub-grid model:
  τ = ½ (τ₀ + √(τ₀² + 18 √2 C_s² |Π_neq| / ρ)), C_s = 0.17.
- Full-way bounce-back on the body and wheels; free-stream equilibrium at the inlet, top and sides; zero-gradient outlet;
  moving road at the free-stream speed. Fluid slivers thinner than one cell between two walls are filled (they cannot be
  resolved and would inject a spurious oscillating force).
- Forces by momentum exchange on the links entering the body, in gauge form (the rest population is subtracted), excluding
  the tyre contact rows; Cd and Cl are referenced to the voxelised frontal area and averaged over the last 30 % of the run.
- Collision and streaming are fused into one CUDA kernel (one thread per cell) on NVIDIA GPUs; NumPy arrays otherwise.
- Resolutions: draft (36 cells along the car, Re 1.2·10³), standard (72, Re 3·10³), fine (104, Re 5·10³).

Honest scope: the lattice Reynolds number is 10³–10⁴, far below a real car (10⁶–10⁷), so boundary layers are thick and
separation can differ. Absolute Cd is indicative; use the tunnel to compare shapes at one resolution and to see where the
flow stagnates, separates and forms the wake.

## Verification and validation (`autoeng.validation`)

The Accuracy page publishes three layers of evidence; `uv run python -m autoeng.validation --write` regenerates the
shipped report (`backend/src/autoeng/validation/published.json`), and any user can re-run it on their own GPU.

| Layer | Case | Reference | Result |
|---|---|---|---|
| Verification | Energy balance, P = T·ω, turbo shaft balance | Conservation laws | Exact (round-off) |
| Verification | I4, I6, cross- and flat-plane V8 shaking forces | Closed-form results | Exact |
| Verification | Euler and Johnson column stresses | Classic formulas | Exact |
| Validation | Sphere drag, Re 100 and 300 | Clift & Gauvin (1971) standard drag curve | +5.4 %, +3.1 %; lift 0 by symmetry |
| Validation | Ahmed body, 0° / 25° / 35° slant | Ahmed, Ramm & Faltin (1984), SAE 840300 | +217 % to +274 %; slant trend not reproduced |
| Field | Uncalibrated torque error on users' shared dyno runs | Their measurements | Grows with every shared calibration |

Reading the results: the solver is sound at the Reynolds numbers it resolves (sphere), but car bodies at
Re ≈ 10⁶ need turbulent, wall-resolved flow that a laptop-sized lattice cannot provide, so tunnel Cd is indicative
and the app does not write it into the vehicle model. Drag for performance predictions should come from a wind
tunnel or coast-down test, entered as a measured value.
