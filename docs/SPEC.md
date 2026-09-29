# AUTOMOTIVE ENGINEERING PLATFORM

## Master Project Context, Vision, Architecture, and Development Specification

---

# 1. PROJECT VISION

We are building a long-term automotive engineering platform, initially delivered as a web application.

This is NOT intended to be merely:

* a car information website
* a car modification recommendation website
* a virtual car configurator
* a simple car simulator
* an AI chatbot about automobiles
* a normal CAD application

The long-term goal is to build an **automotive engineering environment** where a user can:

1. Learn how an automobile and its components work.
2. Start with an existing real automobile and modify it.
3. Start from a completely blank vehicle and design an automobile from scratch.
4. Design individual components.
5. Select or invent/define materials.
6. Assemble components into complete systems.
7. Simulate the physical behavior of those systems.
8. Determine loads, stresses, temperatures, limits, and failure regions.
9. Test alternative designs and materials.
10. Optimize a vehicle against engineering requirements.
11. Connect the simulation to real-world measurements.
12. Eventually manufacture a component/vehicle and compare experimental results with simulation.
13. Build a validated digital twin of the real automobile.

The central philosophy is:

> DESIGN → MATERIAL → PHYSICS → SIMULATION → OPTIMIZATION → MANUFACTURING → REAL TEST → DIGITAL TWIN

The platform should bridge the gap between automotive enthusiasts, mechanics, engineers, developers, researchers, students, and eventually automotive manufacturers.

---

# 2. CORE PRODUCT IDEA

The fundamental question the platform should answer is:

> "What happens if I build or change this?"

Examples:

* What happens if I increase turbo boost?
* What happens if I change the compressor?
* What happens if I change the piston material?
* What happens if I make the chassis thinner?
* What happens if I replace steel with aluminum?
* What happens if I use a carbon-fiber composite?
* What happens if I change wheel size?
* What happens if I change suspension geometry?
* What happens if I change gear ratios?
* What happens if I increase battery capacity?
* What happens if I change the motor?
* What happens if I redesign the brake?
* What happens if I build an entirely new vehicle?
* Can a newly proposed material survive a particular load case?
* Which parts become the limiting components after a modification?
* What components must be upgraded to achieve a target power/performance?

The system must propagate changes through the vehicle rather than evaluating components independently.

---

# 3. TWO PRIMARY WORKFLOWS

The platform must support two major modes.

## MODE A — EXISTING VEHICLE

User selects a real vehicle:

Manufacturer
→ Model
→ Year
→ Variant
→ Engine / Motor
→ Transmission

Then receives a digital representation.

The user can modify:

* engine
* turbo
* intake
* exhaust
* ECU parameters
* cooling
* fuel system
* transmission
* differential
* clutch
* suspension
* brakes
* wheels
* tires
* chassis
* body
* materials
* battery
* electric motor
* aerodynamics

The system calculates the consequences.

---

## MODE B — BUILD A VEHICLE FROM SCRATCH

The user starts with:

"New Vehicle Project"

Then defines:

* vehicle type
* dimensions
* wheelbase
* track width
* seating
* target mass
* target power
* target torque
* target range
* target acceleration
* target top speed
* target cost
* drivetrain
* powertrain
* safety requirements
* manufacturing constraints

The user then designs:

Vehicle architecture
→ chassis
→ body
→ powertrain
→ transmission
→ suspension
→ steering
→ brakes
→ wheels/tires
→ thermal system
→ electrical system
→ electronics
→ interior
→ aerodynamic system

The final result is a complete digital vehicle.

---

# 4. CENTRAL CONCEPT: DIGITAL VEHICLE

Every vehicle should be represented as a structured digital object.

Example:

```
Vehicle
├── Configuration
├── Geometry
├── Chassis
├── Body
├── Powertrain
├── Transmission
├── Differential
├── Driveshaft
├── Suspension
├── Steering
├── Brakes
├── Wheels
├── Tires
├── Cooling
├── Fuel system
├── Electrical system
├── Battery
├── ECU / controller
├── Materials
├── Sensors
├── Manufacturing information
├── Simulation history
├── Measurements
└── Modification history
```

The vehicle is not just a 3D model.

It is simultaneously:

1. Geometry
2. Mechanical system
3. Thermal system
4. Electrical system
5. Material system
6. Manufacturing system
7. Physics model
8. Data structure
9. Digital twin

---

# 5. COMPONENT GRAPH

The platform must represent the automobile as an interconnected engineering graph.

Example:

Turbocharger
→ compressor
→ intake
→ intercooler
→ cylinder
→ combustion
→ crankshaft
→ transmission
→ differential
→ driveshaft
→ wheel
→ tire
→ road

Thermal path:

Combustion
→ engine block
→ coolant
→ radiator
→ ambient

Electrical path:

Battery
→ inverter
→ motor
→ gearbox
→ wheels

Mechanical load path:

Tire
→ wheel
→ hub
→ suspension
→ chassis

Every component should know:

* what it is connected to
* what loads it receives
* what loads it generates
* what material it uses
* what physical models apply to it
* what limits it has
* what failure modes are relevant

---

# 6. COMPONENT DIGITAL PASSPORT

Every engineering component should have a structured digital description.

Example:

TURBOCHARGER

Geometry:

* compressor diameter
* turbine diameter
* shaft diameter
* blade geometry
* housing geometry
* A/R

Material:

* turbine material
* shaft material
* housing material

Performance:

* pressure ratio
* mass flow
* compressor efficiency
* turbine efficiency
* shaft speed

Limits:

* maximum RPM
* maximum temperature
* maximum pressure
* surge limit
* choke limit

Failure modes:

* overspeed
* surge
* bearing failure
* thermal failure
* shaft failure

The same concept must apply to:

* piston
* connecting rod
* crankshaft
* gearbox
* brake disc
* control arm
* chassis member
* battery
* motor
* suspension spring
* damper
* wheel
* tire
* body panel
* etc.

---

# 7. MATERIAL ENGINE

Materials are a first-class component of the platform.

The platform must allow users to select existing materials and eventually define experimental/new materials.

Example properties:

* density
* Young's modulus
* Poisson ratio
* yield strength
* ultimate tensile strength
* thermal conductivity
* specific heat
* coefficient of thermal expansion
* fatigue properties
* fracture properties
* temperature limits
* corrosion properties
* manufacturing method
* cost
* availability

Examples:

* steel
* aluminum
* titanium
* magnesium
* carbon fiber composites
* glass fiber composites
* ceramics
* polymers
* nickel alloys
* Inconel
* experimental materials

Users should be able to create a custom material dataset.

However, custom material data must clearly be marked as:

* user supplied
* experimentally measured
* manufacturer supplied
* literature derived
* estimated
* unknown

The system must never pretend uncertain material properties are verified facts.

---

# 8. MATERIAL EXPERIMENTATION

One important feature is:

> "What if I use a completely different material?"

Example:

Steel control arm
→ Aluminum control arm
→ Titanium control arm
→ Carbon composite
→ User-defined material

For each material, calculate/reason about:

* mass
* stiffness
* stress
* deformation
* thermal behavior
* fatigue
* manufacturing feasibility
* cost
* durability

The platform should identify where the material appears suitable or unsuitable based on the selected engineering models and assumptions.

It must not make unsupported claims merely because an AI model believes a material is appropriate.

---

# 9. CAD / GEOMETRY SYSTEM

The long-term product requires a CAD-like environment.

Users should be able to:

* create geometry
* modify geometry
* create parts
* create assemblies
* define dimensions
* define thickness
* define holes
* define joints
* define constraints
* position components
* assemble components
* inspect geometry
* visualize internal components

The initial version does NOT need to replace professional CAD systems.

Start with a simplified engineering geometry system.

Later integrate or develop more sophisticated:

* parametric CAD
* mesh generation
* surface modeling
* solid modeling
* assemblies
* tolerances

The geometry must eventually feed directly into simulation.

---

# 10. PHYSICS ENGINE

The physics engine is the heart of the platform.

Do NOT use an LLM as the primary physics calculator.

Use actual engineering equations, numerical methods, and validated simulation models.

Potential domains:

## Thermodynamics

* pressure
* temperature
* heat
* efficiency
* energy

## Fluid mechanics

* pressure drop
* flow rate
* turbulence approximations
* compressor behavior
* turbine behavior

## Combustion

* air/fuel ratio
* combustion energy
* cylinder pressure
* temperature

## Mechanical engineering

* stress
* strain
* deformation
* torque
* forces
* vibration

## Materials

* yielding
* fatigue
* thermal expansion
* fracture

## Vehicle dynamics

* acceleration
* braking
* cornering
* weight transfer
* traction
* suspension

## Electrical engineering

* voltage
* current
* power
* battery behavior
* motor behavior

## Thermal engineering

* coolant
* radiator
* engine temperature
* battery temperature
* brake temperature

---

# 11. SIMULATION HIERARCHY

Do not attempt extremely expensive simulations immediately.

Use multiple fidelity levels.

LEVEL 1:
Simple analytical equations

LEVEL 2:
Reduced-order models

LEVEL 3:
Numerical engineering models

LEVEL 4:
FEA

LEVEL 5:
CFD

LEVEL 6:
High-fidelity multiphysics

This allows the platform to remain usable.

For example:

Quick simulation:
seconds

Detailed simulation:
minutes

High-fidelity simulation:
potentially hours

---

# 12. ENGINE SIMULATION

The first serious simulation target should be a turbocharged internal-combustion engine because it combines many engineering domains.

Model:

* displacement
* bore
* stroke
* compression ratio
* RPM
* volumetric efficiency
* boost
* AFR
* fuel
* ignition
* compressor
* turbine
* intercooler
* exhaust

Basic relationships may include:

P = Tω

PV = nRT

compressor pressure ratio

compressor efficiency

turbine efficiency

air mass flow

fuel energy

etc.

Eventually use empirical maps and higher-fidelity engine models.

---

# 13. VIRTUAL DYNO

Create a virtual dyno.

The system should generate:

* torque vs RPM
* power vs RPM
* boost vs RPM
* airflow vs RPM
* fuel consumption
* thermal behavior

Users can compare:

STOCK
vs
MODIFIED
vs
TARGET

Example:

Original:
250 hp

Modified:
310 hp

But results must include uncertainty where appropriate.

Never present a simulation as exact real-world performance.

---

# 14. WHAT-IF ENGINE

This is one of the most important features.

User changes:

Boost:
1.0 bar → 1.5 bar

System propagates:

boost
→ airflow
→ compressor behavior
→ intake temperature
→ cylinder pressure
→ combustion
→ torque
→ crankshaft load
→ transmission load
→ clutch load
→ thermal load
→ cooling requirement

The result should identify affected components.

Example:

ENGINE:
increased load

TURBO:
higher operating point

COOLING:
higher heat rejection

CLUTCH:
higher torque requirement

TRANSMISSION:
higher load

PISTON:
higher cylinder pressure

The system should identify which components become limiting.

---

# 15. ENGINEERING LIMIT / THRESHOLD SYSTEM

Every component should eventually have engineering limits.

Examples:

* maximum stress
* maximum temperature
* maximum RPM
* maximum pressure
* maximum torque
* fatigue limit
* deformation limit
* thermal limit

Conceptually:

Safety Factor:

SF = allowable / actual

The platform should report:

* operating region
* warning region
* critical region
* predicted failure region

But the thresholds must come from documented engineering data/models whenever possible.

---

# 16. LOAD CASE ENGINE

Components must be tested under multiple scenarios.

Examples:

* normal driving
* hard acceleration
* hard braking
* cornering
* bump
* pothole
* curb impact
* aerodynamic load
* thermal cycle
* vibration
* fatigue cycles
* crash scenarios where appropriate and sufficiently validated

The platform should allow:

Component
→ Load cases
→ Simulation
→ Worst case
→ Design decision

---

# 17. SYSTEM-LEVEL PROPAGATION

Changing one part should potentially affect many other systems.

Example:

Chassis material:

Steel
→ Carbon composite

Potential propagation:

density
→ vehicle mass
→ center of gravity
→ weight distribution
→ suspension loads
→ tire loads
→ braking
→ acceleration
→ energy consumption
→ range

Also:

material
→ manufacturing process
→ cost
→ repairability
→ thermal behavior
→ fatigue behavior

This dependency propagation is a core feature.

---

# 18. VEHICLE OPTIMIZATION

Once simulation works, add optimization.

User defines requirements:

Mass < target
Power > target
Acceleration < target
Cost < target
Safety factor > target
Range > target

The system searches design variables:

* geometry
* material
* thickness
* motor
* engine
* turbo
* battery
* gear ratios
* aerodynamics
* suspension parameters

The system generates candidate designs.

Optimization should support constraints.

Conceptually:

minimize objective

subject to engineering constraints.

Eventually support multi-objective optimization:

* minimum mass
* minimum cost
* maximum performance
* maximum efficiency
* maximum durability

Do not present one design as universally "best"; show trade-offs and let the user choose the priorities.

---

# 19. MANUFACTURING ENGINE

A physically valid design is not automatically manufacturable.

Eventually evaluate:

* CNC machining
* casting
* forging
* sheet-metal forming
* welding
* composite layup
* additive manufacturing
* injection molding

Consider:

* minimum thickness
* tolerances
* tool access
* draft angle
* manufacturing process
* material availability
* cost
* joining methods

The pipeline becomes:

DESIGN
→ PHYSICS
→ MANUFACTURABILITY
→ COST
→ PROTOTYPE

---

# 20. REAL-WORLD VALIDATION

The long-term platform must connect digital simulation to physical vehicles.

Potential inputs:

* OBD-II
* CAN bus
* ECU data
* temperature sensors
* pressure sensors
* accelerometers
* strain gauges
* dyno data
* DAQ systems

Example:

Simulation:
Boost = 1.20 bar

Real measurement:
Boost = 1.16 bar

The measured result can be stored.

The system can then calibrate the model.

Pipeline:

SIMULATION
→ PREDICTION
→ MANUFACTURING
→ REAL TEST
→ MEASUREMENT
→ MODEL CALIBRATION
→ BETTER SIMULATION

This is the basis of the digital-twin system.

---

# 21. DIGITAL TWIN

Eventually each physical vehicle can have a digital twin.

Digital twin contains:

* geometry
* configuration
* components
* materials
* modifications
* sensor data
* maintenance
* simulations
* experimental data
* historical versions

The vehicle evolves:

v1 = stock

v2 = intake modification

v3 = turbo modification

v4 = ECU modification

v5 = suspension modification

Every state is preserved.

---

# 22. VERSION CONTROL

The vehicle should behave somewhat like software version control.

Example:

Vehicle v1
→ stock

Vehicle v2
→ new wheels

Vehicle v3
→ new suspension

Vehicle v4
→ turbo upgrade

Users should be able to:

* compare versions
* revert changes
* branch designs
* create experimental variants
* merge validated changes where appropriate

Long-term concept:

> "Git for automotive engineering."

---

# 23. AI ENGINEERING COPILOT

AI should act as an engineering assistant, NOT as the physics source of truth.

Correct architecture:

USER
↓
AI
↓
understand requirement
↓
structured engineering parameters
↓
PHYSICS / CAD / SIMULATION ENGINE
↓
results
↓
AI
↓
explanation

Example:

User:

"Make this car 20% lighter without reducing chassis safety."

AI translates the request into:

* target mass reduction
* preserve selected structural constraints
* identify candidate components
* evaluate material substitutions
* evaluate geometry changes

Then the engineering engine performs the actual calculations.

AI explains the results.

---

# 24. TRUST / ENGINEERING TRUTH LAYER

Every result should indicate its origin.

Example:

Result:
435 HP ± 18 HP

Model:
Engine simulation v2.1

Data sources:
Manufacturer specification
Literature
User measurements

Assumptions:
...

Boundary conditions:
...

Uncertainty:
...

Experimental validation:
Available / unavailable

Every important result should distinguish:

* measured
* calculated
* simulated
* manufacturer supplied
* literature derived
* user supplied
* estimated
* unknown

This is essential for engineers and researchers.

---

# 25. KNOWLEDGE GRAPH

Build an automotive engineering knowledge graph.

Example:

Piston
→ made_of → forged aluminum

Piston
→ connected_to → connecting rod

Piston
→ exposed_to → cylinder pressure

Piston
→ limited_by → temperature

Piston
→ failure_mode → fatigue

Piston
→ affects → engine performance

This knowledge graph connects:

* components
* materials
* physics
* failure modes
* manufacturing
* simulation models
* vehicles

---

# 26. EDUCATIONAL MODE

The same engineering engine should be usable for education.

A component can have multiple explanation levels.

BEGINNER:

"Turbochargers use exhaust energy to compress intake air."

ENGINEER:

show:

* pressure ratio
* mass flow
* efficiency
* shaft speed
* temperature

RESEARCH MODE:

show:

* equations
* assumptions
* boundary conditions
* numerical model
* uncertainty
* references
* experimental validation

Thus the same platform serves:

* enthusiasts
* students
* mechanics
* engineers
* developers
* researchers

---

# 27. USER INTERFACE

Long-term UI:

```
┌───────────────────────────────────────────────────────────┐
│ PROJECT │ DESIGN │ MATERIAL │ SIMULATE │ ANALYZE │ TEST   │
├───────────────┬───────────────────────────────┬───────────┤
│ COMPONENTS    │                               │ PROPERTIES│
│               │                               │           │
│ Body          │          3D VEHICLE          │ Material  │
│ Chassis       │                               │           │
│ Engine        │                               │ Thickness │
│ Motor         │                               │           │
│ Battery       │                               │ Stress    │
│ Suspension    │                               │           │
│ Brakes        │                               │ Temp      │
│ Wheels        │                               │           │
├───────────────┴───────────────────────────────┴───────────┤
│ FEA │ CFD │ THERMAL │ DYNAMICS │ DYNO │ OPTIMIZATION     │
└───────────────────────────────────────────────────────────┘
```

---

# 28. TECHNICAL ARCHITECTURE

Initial architecture can be:

Frontend:

* React
* Next.js
* TypeScript
* Three.js/WebGL/WebGPU

Backend:

* Python
* FastAPI

Engineering:

* NumPy
* SciPy
* JAX/PyTorch where useful

Database:

* PostgreSQL

Object/asset storage:

* S3-compatible storage

Task execution:

* background workers / job queue

Simulation:

* Python initially
* C++/Rust for performance-critical components later

3D:

* Three.js initially
* WebGPU where useful

Later:

* FEA solver
* CFD solver
* mesh generation
* multiphysics systems

---

# 29. DATABASE CONCEPT

Core entities:

Vehicle
Manufacturer
Model
Variant
Component
Assembly
Material
Geometry
Simulation
LoadCase
Measurement
Modification
ManufacturingProcess
Sensor
Experiment
FailureMode
PhysicsModel
Project
User

Relationships:

Vehicle
→ contains → Assembly

Assembly
→ contains → Component

Component
→ uses → Material

Component
→ has → Geometry

Component
→ tested_under → LoadCase

LoadCase
→ evaluated_by → Simulation

Simulation
→ produces → Result

Vehicle
→ has → Modification

Vehicle
→ has → Measurement

Measurement
→ validates → Simulation

---

# 30. FIRST MVP

Do NOT attempt the entire platform immediately.

Build a very small but technically meaningful prototype.

Recommended first vertical:

# TURBOCHARGED ENGINE DESIGN LAB

Allow the user to:

1. Create an engine.
2. Define displacement.
3. Define bore/stroke.
4. Define compression ratio.
5. Define RPM.
6. Define turbocharger.
7. Define boost.
8. Define intercooler.
9. Define fuel.
10. Run simulation.
11. Generate torque curve.
12. Generate power curve.
13. Estimate thermal load.
14. Show component limits.
15. Change parameters.
16. Compare designs.

Then add a simple 3D representation.

This becomes the proof of concept.

---

# 31. SECOND MVP STAGE

Add:

* transmission
* clutch
* differential
* driveshaft
* wheels
* tires
* brakes
* suspension
* chassis

Now the platform can simulate an entire basic vehicle.

---

# 32. THIRD STAGE

Add:

* material substitution
* component geometry
* simplified FEA
* thermal analysis
* vehicle dynamics
* optimization

Now users can actually DESIGN parts.

---

# 33. FOURTH STAGE

Add:

* full 3D assemblies
* more advanced CAD
* CFD
* advanced FEA
* manufacturing constraints

---

# 34. FIFTH STAGE

Add:

* OBD
* CAN
* sensors
* dyno
* real-world testing
* digital twins

---

# 35. COMMUNITY

Eventually users can publish builds.

Example:

"My 600 HP Civic"

Others can inspect:

* components
* materials
* simulations
* modifications
* dyno results
* real measurements
* cost
* failures
* lessons learned

Engineers can publish:

* designs
* experiments
* materials
* models

Researchers can publish:

* simulation models
* experimental datasets
* validated components

Mechanics can publish:

* real-world builds
* diagnostics
* modifications

---

# 36. FUTURE MARKETPLACE

Eventually:

User requirement
↓
Engineering specification
↓
Compatible components
↓
Manufacturers
↓
Suppliers

Example:

"I need a clutch that can withstand approximately X Nm under this load profile."

The system can show components whose documented specifications are relevant.

The platform can eventually connect engineering decisions with actual parts and manufacturing.

---

# 37. CORE DIFFERENTIATOR

Do not position the product primarily as:

"A website that tells you about cars."

The stronger long-term concept is:

> "An engineering platform where you can design, simulate, modify, optimize, and validate an automobile."

The educational content is one layer of the platform.

The deeper value is:

DATA
+
CAD
+
PHYSICS
+
MATERIALS
+
SIMULATION
+
OPTIMIZATION
+
REAL-WORLD VALIDATION

---

# 38. CORE DATA LOOP

The central architecture should always follow:

USER IDEA
↓
ENGINEERING REQUIREMENTS
↓
DESIGN
↓
MATERIAL
↓
GEOMETRY
↓
SYSTEM ASSEMBLY
↓
PHYSICS MODEL
↓
SIMULATION
↓
LIMIT / FAILURE ANALYSIS
↓
OPTIMIZATION
↓
MANUFACTURING
↓
REAL TEST
↓
MEASUREMENT
↓
DIGITAL TWIN
↓
MODEL CALIBRATION
↓
IMPROVED DESIGN

---

# 39. DEVELOPMENT PRINCIPLES

1. Do not attempt the entire system at once.

2. Build one complete engineering vertical first.

3. Prefer physically meaningful models over flashy AI-generated predictions.

4. Keep assumptions explicit.

5. Keep uncertainty explicit.

6. Distinguish measured, calculated, simulated, and estimated data.

7. Every engineering result should be traceable to its model and inputs.

8. Use modular physics models.

9. Design the architecture so additional physics domains can be plugged in later.

10. Design the database around engineering relationships rather than just web pages.

11. CAD geometry should eventually connect directly to simulation.

12. Materials should be represented independently from components.

13. Components should be reusable across vehicle designs.

14. Vehicle configurations should be version controlled.

15. Real-world measurements should eventually feed back into simulation.

16. AI should assist engineering workflows but should not replace engineering solvers.

17. Safety-critical results must be presented as engineering analysis, not guaranteed real-world safety certification.

---

# 40. LONG-TERM VISION

The final platform should allow something like this:

A user says:

"Design a lightweight two-seat electric sports car."

The system creates an engineering project.

The user specifies:

Mass target
Power target
Range
Top speed
Acceleration
Cost
Material preferences

The platform proposes architectures.

The user selects one.

The user designs:

Chassis
Body
Battery
Motor
Suspension
Brakes
Wheels
Cooling
Aerodynamics

The system simulates them.

The user changes materials.

The system recalculates the vehicle.

The user changes geometry.

The system recalculates the vehicle.

The user runs optimization.

The system generates candidate designs.

The user selects a design.

The platform generates manufacturing information.

A physical prototype is manufactured.

Sensors collect real data.

The data is fed back into the platform.

The digital vehicle becomes a digital twin.

The simulation model is calibrated.

The next design becomes better.

That is the ultimate product vision.

---

# 41. ONE-SENTENCE DESCRIPTION

The platform can ultimately be described as:

> **A digital automotive engineering environment where users can learn, design, modify, simulate, optimize, manufacture, and validate complete automobiles and their individual components using real engineering models, materials, CAD, physics, and real-world data.**

---

# 42. GUIDELINES FOR EVERYONE WORKING ON THIS PROJECT

When helping develop this project:

* Understand the complete vision before proposing architecture.
* Do not reduce the project to a simple car configurator.
* Do not reduce it to a modification calculator.
* Do not assume the platform only works with existing vehicles.
* Support both existing vehicles and ground-up vehicle design.
* Treat materials as first-class engineering entities.
* Treat geometry as connected to physics.
* Treat components as interconnected systems.
* Use actual engineering equations/models wherever possible.
* Never invent engineering specifications.
* Clearly label assumptions and uncertainty.
* Separate AI reasoning from physics calculations.
* Build modularly so the system can eventually support FEA, CFD, thermal analysis, vehicle dynamics, electrical simulation, and manufacturing.
* Prioritize a working vertical prototype over an enormous unfinished architecture.
* Every new feature should fit into the overall pipeline:

DESIGN
→ MATERIAL
→ GEOMETRY
→ SYSTEM
→ PHYSICS
→ SIMULATION
→ LIMITS
→ OPTIMIZATION
→ MANUFACTURING
→ REAL TEST
→ DIGITAL TWIN

The first implementation should focus on proving this pipeline with a small but technically rigorous automotive subsystem before expanding to the complete automobile.
