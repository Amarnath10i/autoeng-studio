"""A vehicle is a graph of component instances wired port-to-port (spec §4, §5).

This is the generic "digital vehicle" data structure. It supports both workflows
(spec §3): starting from a template of an existing layout, or from an empty
vehicle built up component by component. Physics models find what they need by
walking the graph (for example the driveline chain along rotation ports), so the
same data serves the engine lab, vehicle performance and later domains.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from autoeng.platform.catalog import CATALOG, PortKind

SCHEMA_VERSION = 1


class ComponentInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    name: str = ""
    params: dict[str, Any] | None = None
    notes: str = ""


class Connection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # "component.port"
    target: str = Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")


class VehicleDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    kind: str = "vehicle"
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    vehicle_type: str = "passenger_car"
    components: dict[str, ComponentInstance] = Field(default_factory=dict)
    connections: list[Connection] = Field(default_factory=list)
    targets: dict[str, float] = Field(default_factory=dict)  # e.g. {"accel_0_100_s": 6.0, "top_speed_kmh": 240}

    @model_validator(mode="after")
    def _validate(self) -> VehicleDesign:
        errors: list[str] = []
        for cid, comp in self.components.items():
            if not cid.replace("_", "").isalnum() or not cid.islower():
                errors.append(f"component id '{cid}': use lowercase letters, digits and underscores")
            ctype = CATALOG.get(comp.type)
            if ctype is None:
                errors.append(f"{cid}: unknown component type '{comp.type}'")
                continue
            if ctype.params_model is not None and comp.params is not None:
                try:
                    comp.params = ctype.params_model.model_validate(comp.params).model_dump(mode="json")
                except ValueError as exc:
                    errors.append(f"{cid} ({ctype.name}): {exc}")
        used: set[str] = set()
        for conn in self.connections:
            kinds = []
            for end in (conn.source, conn.target):
                cid, port = end.split(".")
                comp = self.components.get(cid)
                ctype = CATALOG.get(comp.type) if comp else None
                p = ctype.port(port) if ctype else None
                if p is None:
                    errors.append(f"connection {conn.source} → {conn.target}: no port '{end}'")
                    kinds.append(None)
                    continue
                if end in used and p.kind is not PortKind.MOUNT:
                    errors.append(f"port '{end}' is connected more than once")
                used.add(end)
                kinds.append(p.kind)
            if None not in kinds and kinds[0] is not kinds[1]:
                errors.append(f"connection {conn.source} → {conn.target}: cannot join {kinds[0]} to {kinds[1]}")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def of_type(self, type_id: str) -> list[tuple[str, ComponentInstance]]:
        return [(cid, c) for cid, c in self.components.items() if c.type == type_id]

    def neighbours(self, cid: str, kind: PortKind) -> list[str]:
        out = []
        for conn in self.connections:
            a, b = conn.source.split(".")[0], conn.target.split(".")[0]
            for this, other, end in ((a, b, conn.source), (b, a, conn.target)):
                if this != cid:
                    continue
                ctype = CATALOG[self.components[this].type]
                port = ctype.port(end.split(".")[1])
                if port and port.kind is kind:
                    out.append(other)
        return out

    def driveline_chain(self) -> list[str]:
        """Component ids along rotation ports, starting at the power source."""
        sources = [cid for cid, c in self.components.items() if c.type in ("engine_turbo_si", "electric_motor")]
        if not sources:
            return []
        chain, seen = [sources[0]], {sources[0]}
        while True:
            nxt = [n for n in self.neighbours(chain[-1], PortKind.ROTATION) if n not in seen]
            if not nxt:
                return chain
            chain.append(nxt[0])
            seen.add(nxt[0])

    def architecture_report(self) -> dict:
        """What is present, what can be simulated, and what is missing (for the UI)."""
        planned = [cid for cid, c in self.components.items() if CATALOG[c.type].status == "planned"]
        missing_params = [cid for cid, c in self.components.items()
                          if CATALOG[c.type].params_model is not None and c.params is None]
        chain = self.driveline_chain()
        chain_types = [self.components[c].type for c in chain]
        required = ["engine_turbo_si", "clutch", "gearbox", "final_drive", "wheel_tire"]
        longitudinal_ready = (
            all(t in chain_types for t in required)
            and bool(self.of_type("body"))
            and not any(c in missing_params for c in chain + [b for b, _ in self.of_type("body")])
        )
        free_ports = []
        connected = {e for conn in self.connections for e in (conn.source, conn.target)}
        for cid, c in self.components.items():
            for p in CATALOG[c.type].ports:
                if f"{cid}.{p.name}" not in connected and p.kind in (PortKind.ROTATION, PortKind.DC, PortKind.AC):
                    free_ports.append(f"{cid}.{p.name}")
        return {
            "driveline_chain": chain,
            "planned_components": planned,
            "components_missing_params": missing_params,
            "unconnected_power_ports": free_ports,
            "models": {
                "engine.turbo_si_mvem": bool(self.of_type("engine_turbo_si")),
                "vehicle.longitudinal": longitudinal_ready,
            },
        }
