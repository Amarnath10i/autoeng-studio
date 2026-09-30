# AutoEng Studio

A digital automotive engineering environment: design, modify, simulate, analyse and validate automobiles and their
components with real engineering models, explicit uncertainty and real-world data.

> DESIGN → MATERIAL → PHYSICS → SIMULATION → LIMITS → OPTIMISATION → REAL TEST → DIGITAL TWIN

The full product vision is in [docs/SPEC.md](docs/SPEC.md); the physics is documented in [docs/MODELS.md](docs/MODELS.md);
market context, risks and priorities are in [docs/MARKET_ANALYSIS.md](docs/MARKET_ANALYSIS.md).

## What it does today

**Vehicle projects (build from a template or from a blank vehicle)**
- Component graph: engine, clutch, gearbox, final drive, wheels & tyres, body, cooling circuit and front brakes, wired
  port-to-port with type checking (shaft, air, exhaust, fuel, coolant, electrical, mounts). Battery, motor, inverter,
  suspension, chassis structure and fuel system are already part of the architecture as *planned* components.
- Straight-line performance: 0–100 km/h, quarter mile, top speed, traction limit, gearing, traction diagram, driveline
  loads, with Monte Carlo uncertainty on every number.
- Time-domain scenarios: drive a schedule (highway, mountain pass, track day, hot traffic, top-speed run, or your own)
  second by second, with coolant and brake-disc temperatures, component loads, and the time at which each limit is
  crossed (overheating, brake fade, cannot hold speed).
- Weather studies: one scenario across a grid of ambient temperatures, altitudes and road surfaces in a single batched
  (GPU) ensemble.
- Material studies: same geometry, different material for brake discs and connecting rods, including melting and
  softening checks.
- Body design: sketch the side profile and front section, shape the 3D skin (beltline, tumblehome, corner rounding,
  wheel wells), see it as a lofted quad mesh with a CAD-style wireframe, export STL, or import your own STL/OBJ body.
- Virtual wind tunnel (GPU): full 3D lattice-Boltzmann flow around the lofted or imported body with a moving road;
  drag and lift coefficients, drag at 100 km/h, 3D streamlines with tracer particles, surface pressure, centre-plane and
  plan-view slices, convergence history, and one click to use the measured Cd in the vehicle model.

**Engine lab (spark-ignition engines)**
- Layouts: inline, V, W and flat (boxer) engines with any bank angle, split-pin, cross-plane and flat-plane cranks,
  rendered in 3D with true piston kinematics.
- Balance and firing: primary and secondary shaking forces and rocking couples, what counterweights can cancel, firing
  intervals and order, and package size.
- Induction: turbocharged, naturally aspirated, positive-displacement or centrifugal supercharged (with crank drive power).
- Mean-value engine model with a turbine–compressor power balance (boost builds with rpm; wastegate or turbine-limited),
  combustion energy split, peak cylinder pressure, friction and pumping, fuel system and thermal loads.
- Connecting-rod structural checks from geometry and material: Johnson/Euler buckling, tensile yield with an overspeed
  load case, and Goodman fatigue.
- Virtual dyno with uncertainty bands, comparison against saved versions (stock vs. modified vs. target) and a chart
  builder.
- Limits and safety factors (allowable ÷ load, conservative percentiles, probability of exceedance) with documented
  status bands.
- What-if engine: propagation path through the models, affected components, newly limiting parts.
- Upgrade advisor: strategies to reach a power target, each with the list of parts that need higher ratings.
- Design-space explorer: 2-D sweeps with Monte Carlo at every point (GPU), heatmaps of power, risk and target
  probability.
- Sensitivity ranking: which uncertain inputs matter most, so you know what to measure first.
- Calibration: upload dyno CSVs, fit model parameters, get their confidence intervals and identifiability warnings,
  save the calibrated design as a new version.

**Platform**
- Trust layer: every input carries its source (measured, manufacturer, literature, user, estimated, unknown,
  calibrated, community) and uncertainty; every result lists its models, assumptions and data sources.
- Version control for designs: commits, branches, diffs, three-way merges with conflict resolution, restore.
- Community learning (opt-in): shared calibrations of real engines become learned defaults for similar engines, weighted
  by similarity and reported with an effective sample size.
- Research assistant (optional): web search for material properties and part specifications, returned as cited
  candidates that you review before anything enters the library.
- Bring-your-own compute: pair your own GPU (PC, Kaggle, Colab, cloud VM) with a one-time code; workers connect
  outbound and run jobs with NumPy on CPU or CuPy on NVIDIA GPUs.
- Accounts, projects, materials library, light and dark themes, a table view for every chart.

## Architecture

```
frontend/  Next.js 16 · React 19 · TypeScript · Tailwind 4 · Recharts · three.js
backend/   Python 3.14 · FastAPI · SQLAlchemy 2 · Alembic · NumPy/SciPy · CuPy (optional)
  src/autoeng/
    core/        Param (value + source + uncertainty), sampling
    domain/      engine design schema, fuels, materials, component/channel registry
    physics/     gas dynamics, engine MVEM, connecting rod, longitudinal dynamics, duty cycle (thermal)
    analysis/    simulate, limits, what-if, advisor, calibration, studies (sweeps), propagation graph
    platform/    component catalog, vehicle graph, scenarios, vehicle & scenario simulation
    services/    auth, projects & version control, jobs & workers, community learning, research
    api/         REST endpoints (OpenAPI at /docs)
    worker.py    `autoeng-worker` command for user-owned compute
docs/      spec, model reference, market analysis
```

Physics runs on arrays shaped (samples × operating points), so the same code evaluates one design or a batch of
thousands of design × weather × Monte Carlo combinations. `autoeng.compute` picks NumPy or CuPy per workload.

## Running locally

Requirements: Python 3.14 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm.

**Windows, one click:** double-click `start.cmd`. It installs dependencies, starts the API and the web app in two
windows and opens http://localhost:3000. Create an account on first visit.

Manually, in two terminals:

```bash
# Backend (http://localhost:8000, API docs at /docs)
cd backend
uv sync                      # add --extra gpu for NVIDIA GPU support (CuPy + CUDA runtime wheels)
uv run python -m uvicorn autoeng.api.app:app --reload

# Frontend (http://localhost:3000)
cd frontend
pnpm install
pnpm dev
```

The database defaults to SQLite (`backend/autoeng.db`) and migrates on startup. For PostgreSQL set
`AUTOENG_DATABASE_URL=postgresql+psycopg://user:pass@host/db`. `docker compose up` runs PostgreSQL, the API and the web
app together (see `docker-compose.yml`).

### Configuration (backend environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `AUTOENG_DATABASE_URL` | `sqlite:///./autoeng.db` | Database |
| `AUTOENG_COMPUTE` | `auto` | `auto`, `gpu` or `cpu` |
| `AUTOENG_SERVER_WORKERS` | `2` | In-process job runners |
| `AUTOENG_PUBLIC_URL` | `http://localhost:8000` | URL shown to workers when pairing |
| `AUTOENG_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed web origins |
| `AUTOENG_RESEARCH_API_KEY` | unset | Enables the research assistant |
| `AUTOENG_AUTH_DISABLED` | `false` | Single-user local mode (never on a shared server) |

Frontend: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

### Using your own GPU

1. In the web app open **Compute → Add a worker** to get a one-time pairing code.
2. On the machine with the GPU:
   ```bash
   pip install "autoeng[gpu] @ git+<repo-url>#subdirectory=backend"
   autoeng-worker --server https://your-api --code ABCD-2345
   ```
   In Kaggle or Colab, enable a GPU accelerator and internet access and run the same two lines in a cell. The API must
   be reachable from the worker (deploy it, or expose a local server through a tunnel).
3. Choose the worker in any **Compute** selector (simulate, sweeps, scenarios, studies).

Measured on an RTX 3050 laptop GPU: a 20 × 15 design sweep with 200 samples per point (60 000 engine evaluations) runs in
about 19 s versus about 190 s on the CPU; a weather study of 24 000 vehicle simulations through a 24-minute mountain pass
runs in about 58 s. Small runs stay on the CPU, where GPU launch overhead would dominate.

## Tests

```bash
cd backend && uv run python -m pytest     # physics, API, version control, jobs, workers, scenarios
cd frontend && pnpm lint && pnpm build
```

The physics tests check conservation and consistency (energy balance, P = T·ω, turbo power balance, nozzle inversion,
Johnson/Euler continuity, calibration recovering known parameters, GPU results equal to CPU results), not just that the
code runs.

## Status and roadmap

Built: spec stage 1 (turbo engine lab) in depth, the foundation of stage 2 (vehicle graph, driveline, performance,
thermal duty cycles), material substitution (stage 3), and the validation loop (stage 5: measurements, calibration,
community learning).

Next, in priority order (see the market analysis for the reasoning):
1. Validation programme: real dyno and track datasets, published accuracy per model.
2. Knock and spark timing; compressor-map import (surge, choke, shaft speed); transient spool.
3. Electric powertrain: battery, inverter and motor models on the existing graph.
4. OBD-II/CAN log import and ECU-log based calibration.
5. Chassis: suspension, braking and cornering dynamics; lap-time simulation.
6. Geometry: STEP import, finer aerodynamic grids with wall models, and simplified FEA for components.
7. Teams and organisations, billing, public build pages, surrogate models for in-browser (WebGPU) exploration.

Results are engineering estimates from simplified models, not measurements or safety certification.
