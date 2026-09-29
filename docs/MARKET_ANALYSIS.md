# Market analysis: landscape, usefulness, gaps, risks

*Prepared September 2026. Figures come from the sources listed at the end; market-size reports vary widely between
research firms and should be treated as indicative.*

## 1. Does something like this already exist?

Parts of it exist, spread across very different products. No product found combines them.

| Segment | Examples | What they do well | What they lack (relative to this platform) |
|---|---|---|---|
| Enthusiast engine simulators (desktop) | DynoSim5 (Comp Cams), Performance Trends Engine Analyzer, DeskTop Dyno 5, Virtual Engine Dyno | Cheap; large catalogs of real cams, heads and turbos; claimed ~5 % accuracy vs. dyno for NA engines | Engine only; desktop; no whole-vehicle propagation, thermal time behaviour, uncertainty, calibration loop, versioning or collaboration |
| Professional 1D / system simulation | GT-SUITE (Gamma Technologies), Ricardo WAVE (Realis Simulation), AVL tools | Validated, deep, industry standard | Expensive, expert-only, weeks of model setup; not for enthusiasts, shops or students |
| Cloud CAE | SimScale (browser FEA/CFD, AI features), Onshape + SimScale | Browser-based, collaborative | Generic physics; no automotive system graph, what-if propagation or engine/vehicle domain models. Priced for companies (SimScale commonly quoted at hundreds to ~1,500 USD per user per month; Onshape 1,500–2,500 USD per user per year) |
| Physics AI | PhysicsX (raised 300 M USD), Neural Concept, NVIDIA PhysicsNeMo in SimScale | Fast surrogates for aero, thermal, crash at OEM scale | Enterprise-only; needs large simulation datasets; not a design environment for individuals |
| Vehicle performance / lap time | OptimumLap (free, ~10 parameters, ~10 % lap-time accuracy claim) | Very simple, good for Formula Student | No component physics, materials, limits, thermal or validation loop |
| Games and sandboxes | BeamNG.drive (soft-body physics), Automation (car and engine designer, exports to BeamNG) | Huge enthusiast audience; engaging | Entertainment, not engineering truth: no provenance, uncertainty, limits against documented data, or real-world calibration |
| Open source | OpenWAM (1D gas dynamics) | Free, detailed engine gas dynamics | Research code, hard to use, engine only |
| Digital twin / telematics | Fleet predictive-maintenance and SDV twin vendors | OBD/CAN data, maintenance prediction | Operations focus; no design, physics what-if or modification engineering |

**Conclusion:** the individual capabilities exist, but no product offers, in one browser-based environment at a
prosumer price, a whole-vehicle component graph with change propagation, uncertainty and provenance on every number,
version control for designs, and a measured-data calibration loop. That combination is this platform's position.

## 2. Will it be useful, and for whom?

Useful if (and only if) its predictions earn trust. Buyers ask one question first: *how close is it to my dyno?* The
calibration loop, uncertainty bands and published validation are therefore the core of the product, not extras.

Most promising first customers (wedge), in order:

1. **Tuning shops and serious builders.** Pain: buying parts by trial and error and breaking drivetrains. Value: "what
   must I upgrade for 300 kW?" (upgrade advisor), limits before purchase, calibrated models of customer cars,
   shareable reports. The performance-parts market is estimated at roughly 370–390 billion USD in 2026, about
   two-thirds of it aftermarket (one report); even a small software share is meaningful.
2. **Formula Student and university teams.** Pain: expensive professional licences, little time. Value: engine,
   driveline, thermal and material studies with honest assumptions; version control fits team work; education modes.
3. **Small motorsport and EV start-ups.** Pain: need early concept studies without a GT-SUITE budget. Value:
   design-space sweeps and scenario studies on their own GPUs.
4. **Education and enthusiasts** (top of funnel): the beginner/engineer/research explanation levels and public build
   pages (spec §35).

Later: suppliers and the parts marketplace (spec §36), once specifications and validation data are credible.

## 3. What must change to become worthy of a start-up

Built today: the engine lab in depth; the vehicle graph with driveline, performance and thermal duty cycles; material
substitution; calibration and community learning; version control; GPU and bring-your-own compute. To win customers:

| Priority | Change | Why |
|---|---|---|
| 1 | **Validation programme:** partner with 3–5 dyno shops and a Formula Student team; publish accuracy per model and engine type | Credibility is the product. Also feeds community priors |
| 2 | **Knock, spark timing, compressor-map import, transient spool** | Knock is what really limits boost and compression in turbo engines; maps define surge and choke; users will notice these gaps first |
| 3 | **Electric powertrain** (battery, inverter, motor, thermal) | The market is moving to EVs; the architecture already has these components planned |
| 4 | **Real-vehicle data (spec mode A)** with licensed or crowdsourced specifications and provenance | "Start from my car" is the easiest onboarding; data must be licensed, not scraped |
| 5 | **OBD-II / CAN / ECU log import** (common tuner log formats) | Turns every customer car into calibration data |
| 6 | **Chassis dynamics and lap time** (suspension, braking, cornering, tyres) | Needed for track users and Formula Student |
| 7 | **Business plumbing:** organisations and teams, billing, quotas, audit logs, SSO, rate limits | Required for paying teams and schools |
| 8 | **Geometry:** STEP import and simplified FEA (open-source solvers) for components | Connects CAD to the physics (spec §9) |

## 4. Current and future technology to use

| Trend | How the platform uses it |
|---|---|
| **GPU-batched simulation** | Already built: design sweeps, weather studies and Monte Carlo run as batched array maths (CuPy on NVIDIA GPUs); about 10× faster than CPU on a laptop RTX 3050 |
| **Bring-your-own compute** | Already built: users pair their own PC, Kaggle or Colab GPU; keeps hosting costs low for a start-up |
| **Physics-AI surrogates** (PhysicsX, NVIDIA PhysicsNeMo) | Train fast surrogates on the platform's own physics runs plus measured data, for real-time exploration and optimisation, while the physics stays the source of truth |
| **WebGPU in the browser** (ONNX Runtime Web WebGPU execution provider, Chromium 113+; still marked experimental) | Run those surrogates on the user's own GPU inside the browser, with no server cost |
| **Language models with web research** | Already built: the research assistant finds cited material and part data for human review. Next: a copilot that turns requests ("make it 20 % lighter") into parameter changes the solvers evaluate |
| **Digital twins from vehicle data** (OBD-II, CAN, telematics) | The calibration loop plus versioned designs are the basis of per-vehicle twins |
| **Open-source CAE** (CalculiX, FEniCS, OpenFOAM, OpenCascade) | Component FEA, CFD and CAD import without licence cost |

## 5. Possibilities

- The data network effect: every shared calibration improves defaults for everyone; this compounds and is hard to
  copy.
- A trusted source of "what fails first", with evidence, for the aftermarket: upgrade shopping lists matched to
  documented part ratings (marketplace).
- Education licences (explanation levels, research mode) and Formula Student partnerships as a growth channel.
- Shop tier: customer-facing reports ("your car, calibrated, what the upgrade does, with uncertainty").
- Later: supplier tools (publish validated component data) and OEM/Tier-2 concept studies.

## 6. Drawbacks and risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Accuracy and credibility** | Level-1 models can be wrong; one public miss hurts trust | Uncertainty bands, trust layer, calibration, published validation, never hide assumptions |
| **Liability** | Users may break engines or brakes acting on results; brakes and structures are safety-relevant | Clear "engineering estimate, not certification" terms; no safety sign-off claims; legal review of terms before launch |
| **Data rights** | Manufacturer specifications and part catalogs are often proprietary | License data, partner with suppliers, or crowdsource with provenance; the research assistant cites sources and needs user review |
| **Scope** | The vision spans CAD, FEA, CFD, EV, dynamics and marketplace; spreading thin kills start-ups | Stay vertical: win tuners and students with engine + driveline + thermal before breadth |
| **EV transition** | Combustion-engine tuning shrinks over the long term | Build the EV powertrain next; the graph already supports it |
| **Competition** | Incumbents can add cloud features; games own enthusiast attention | Differentiate on trust, calibration with real data, community data and price |
| **Price sensitivity** | Enthusiasts pay little; professionals demand validation and integrations | Freemium engine lab; paid tiers for studies, compute, teams and reports |
| **Community data quality** | Shared calibrations can be wrong or malicious | Weight by fit quality, reject outliers, reputation, effective-sample-size reporting (already shown to users) |
| **Compute cost and abuse** | GPU time is expensive | Bring-your-own compute, quotas, job limits (already enforced per request) |
| **Model hallucination** | Language-model research can invent numbers | Values need a verbatim quote and URL; URLs are checked against the pages actually retrieved; user review is mandatory |

## 7. Suggested business model

- **Free:** engine lab and vehicle performance with limited samples and projects; public build pages.
- **Pro (individuals):** studies, scenarios, sweeps, calibration, unlimited versions, own-GPU workers.
- **Team / education:** organisations, shared projects, roles, classroom licences, Formula Student programme.
- **Shop:** customer vehicle twins, branded reports, log import.
- **Later:** marketplace referrals, only for parts with documented ratings, with neutrality rules to protect trust.

## Sources

- [Comp Cams' DynoSim5 put to the test (EngineLabs)](https://www.enginelabs.com/engine-tech/comp-cams-dynosim5-engine-simulation-software-put-to-the-test/)
- [Engine simulation and modeling software guide (MuscleCar DIY)](https://www.musclecardiy.com/performance/engine-simulation-modeling-software-guide/)
- [Virtual Engine Dyno](http://virtualengine2000.com/)
- [GT-SUITE product options (Gamma Technologies)](https://www.gtisoft.com/gt-suite/product-options)
- [GT-SUITE on MathWorks](https://www.mathworks.com/products/connections/product_detail/gt-suite.html)
- [Realis Simulation academic grants (formerly Ricardo Software)](https://www.realis-simulation.com/support/academia/)
- [SimScale](https://www.simscale.com/) and [SimScale pricing](https://www.simscale.com/product/pricing/)
- [SimScale pricing reviews (Software Advice)](https://www.softwareadvice.com/construction/simscale-profile/)
- [Onshape plans and pricing](https://www.onshape.com/en/pricing)
- [Onshape + SimScale](https://www.onshape.com/en/blog/rapid-design-simulation-directly-browser)
- [SimScale: AI-powered simulation for automotive engineering](https://www.simscale.com/blog/shaping-the-future-of-automotive-engineering-with-ai-powered-simulation/)
- [PhysicsX](https://www.physicsx.ai/) and [PhysicsX 300 M USD raise](https://flairiusnews.com/physicsx-300-million-ai-physics-simulation-engineering-2026/)
- [OptimumLap (OptimumG)](https://optimumg.com/product/optimumlap/)
- [BeamNG.drive](https://beamng.com/) and [BeamNG.drive (Wikipedia)](https://en.wikipedia.org/wiki/BeamNG.drive)
- [Automation (video game)](https://en.wikipedia.org/wiki/Automation_(video_game))
- [OpenWAM](https://openwam.webs.upv.es/docs/)
- [ONNX Runtime WebGPU execution provider](https://onnxruntime.ai/docs/execution-providers/WebGPU-ExecutionProvider.html)
- [Digital twin for vehicles market report](https://dataintelo.com/report/digital-twin-for-vehicles-market)
- [Automotive performance parts market report 2026 (Research and Markets)](https://www.researchandmarkets.com/reports/5995058/automotive-performance-parts-market-report)
- [Automotive performance parts market size (Fairfield Market Research)](https://www.fairfieldmarketresearch.com/report/automotive-performance-parts-market)
