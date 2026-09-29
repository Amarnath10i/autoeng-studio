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

## Straight-line vehicle performance: `vehicle.longitudinal` v1.0.0

- Wheel force per gear: F = T(N) · i_g · i_fd · η / r_w, with N from road speed; launch holds the engine at the launch rpm
  while the clutch slips.
- Resistance: ½ ρ C_d A v² + C_rr m g. Rotating inertia: γ = 1.04 + 0.0025 (i_g i_fd)² (Wong).
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
