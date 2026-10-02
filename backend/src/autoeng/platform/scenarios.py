"""Operating scenarios: weather plus a drive profile, run through time (spec §16 load cases).

A profile is a list of segments (cruise, full throttle, brake, accelerate), each
with a duration and road grade, optionally repeated. Segments are time-based so
every Monte Carlo sample and weather point experiences the same schedule.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

G = 9.80665


class Weather(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambient_temp_c: float = Field(25.0, ge=-40, le=55)
    altitude_m: float = Field(0.0, ge=-400, le=5500)
    headwind_kmh: float = Field(0.0, ge=-100, le=100)
    surface: Literal["dry", "wet", "snow"] = "dry"

    @property
    def pressure_kpa(self) -> float:
        """International Standard Atmosphere, troposphere."""
        return 101.325 * (1.0 - 2.25577e-5 * self.altitude_m) ** 5.25588

    @property
    def friction_factor(self) -> float:
        return {"dry": 1.0, "wet": 0.7, "snow": 0.3}[self.surface]


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["cruise", "full_throttle", "brake", "accelerate", "idle"]
    duration_s: float = Field(gt=0, le=7200)
    speed_kmh: float = Field(0.0, ge=0, le=450)  # cruise/brake/accelerate target
    rate_g: float = Field(0.3, gt=0, le=2.0)  # brake deceleration or acceleration demand
    grade_pct: float = Field(0.0, ge=-30, le=30)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    weather: Weather = Field(default_factory=Weather)
    segments: list[Segment] = Field(min_length=1, max_length=200)
    repeats: int = Field(1, ge=1, le=200)
    initial_speed_kmh: float = Field(0.0, ge=0, le=400)
    cold_start: bool = False  # start with coolant at ambient instead of thermostat temperature
    dt_s: float = Field(0.1, ge=0.02, le=1.0)

    @property
    def duration_s(self) -> float:
        return sum(s.duration_s for s in self.segments) * self.repeats


MODE_CODE = {"cruise": 0, "full_throttle": 1, "brake": 2, "accelerate": 3, "idle": 4}
MAX_STEPS = 200_000


def compile_schedule(sc: Scenario) -> dict[str, np.ndarray]:
    """Per-time-step arrays: mode, target speed (m/s), rate (m/s²), grade (rad)."""
    steps = int(round(sc.duration_s / sc.dt_s))
    if steps > MAX_STEPS:
        raise ValueError(f"Scenario has {steps} steps; increase dt_s or shorten it (max {MAX_STEPS})")
    mode = np.empty(steps, dtype=np.int8)
    target = np.empty(steps)
    rate = np.empty(steps)
    grade = np.empty(steps)
    i = 0
    for _ in range(sc.repeats):
        for seg in sc.segments:
            k = int(round(seg.duration_s / sc.dt_s))
            j = min(i + k, steps)
            mode[i:j] = MODE_CODE[seg.mode]
            target[i:j] = seg.speed_kmh / 3.6
            rate[i:j] = seg.rate_g * G
            grade[i:j] = math.atan(seg.grade_pct / 100.0)
            i = j
    return {"mode": mode[:i], "target": target[:i], "rate": rate[:i], "grade": grade[:i]}


def _sc(name, description, weather, segments, repeats=1, initial=0.0, dt=0.1) -> Scenario:
    return Scenario(name=name, description=description, weather=Weather(**weather),
                    segments=[Segment(**s) for s in segments], repeats=repeats, initial_speed_kmh=initial, dt_s=dt)


BUILTIN: dict[str, Scenario] = {
    "highway_130": _sc(
        "Highway cruise 130 km/h", "30 minutes at a steady 130 km/h on a warm day.",
        {"ambient_temp_c": 30}, [{"mode": "cruise", "speed_kmh": 130, "duration_s": 1800}], initial=130, dt=0.5),
    "mountain_pass": _sc(
        "Mountain pass, hot day", "Climb 12 minutes at 8 % and 80 km/h, then descend at 60 km/h on the brakes.",
        {"ambient_temp_c": 35, "altitude_m": 1500},
        [{"mode": "cruise", "speed_kmh": 80, "duration_s": 720, "grade_pct": 8},
         {"mode": "cruise", "speed_kmh": 60, "duration_s": 720, "grade_pct": -8}], initial=80, dt=0.2),
    "track_day": _sc(
        "Track day session", "Ten hard laps: full-throttle straights and heavy braking.",
        {"ambient_temp_c": 28},
        [{"mode": "full_throttle", "duration_s": 12},
         {"mode": "brake", "speed_kmh": 70, "rate_g": 1.0, "duration_s": 5},
         {"mode": "cruise", "speed_kmh": 70, "duration_s": 6},
         {"mode": "full_throttle", "duration_s": 9},
         {"mode": "brake", "speed_kmh": 90, "rate_g": 0.9, "duration_s": 4},
         {"mode": "cruise", "speed_kmh": 90, "duration_s": 6}], repeats=10, initial=90, dt=0.05),
    "hot_traffic": _sc(
        "Stop-and-go traffic, 42 °C", "Twenty stop-and-go cycles in extreme heat.",
        {"ambient_temp_c": 42},
        [{"mode": "accelerate", "speed_kmh": 40, "rate_g": 0.15, "duration_s": 12},
         {"mode": "cruise", "speed_kmh": 40, "duration_s": 15},
         {"mode": "brake", "speed_kmh": 0, "rate_g": 0.2, "duration_s": 8},
         {"mode": "idle", "duration_s": 25}], repeats=20, dt=0.2),
    "top_speed": _sc(
        "Top-speed run", "Two minutes flat out from 60 km/h.",
        {"ambient_temp_c": 20}, [{"mode": "full_throttle", "duration_s": 120}], initial=60, dt=0.05),
    "urban_cycle": _sc(
        "Urban cycle", "City driving: gentle pull-aways to 50 km/h, short cruises, lights and junctions.",
        {"ambient_temp_c": 22},
        [{"mode": "accelerate", "speed_kmh": 50, "rate_g": 0.12, "duration_s": 15},
         {"mode": "cruise", "speed_kmh": 50, "duration_s": 30},
         {"mode": "brake", "speed_kmh": 0, "rate_g": 0.15, "duration_s": 10},
         {"mode": "idle", "duration_s": 20},
         {"mode": "accelerate", "speed_kmh": 30, "rate_g": 0.1, "duration_s": 9},
         {"mode": "cruise", "speed_kmh": 30, "duration_s": 20},
         {"mode": "brake", "speed_kmh": 0, "rate_g": 0.12, "duration_s": 8}], repeats=12, dt=0.2),
    "autobahn": _sc(
        "Autobahn run 200 km/h", "Twenty minutes at a sustained 200 km/h with two hard slow-downs for traffic.",
        {"ambient_temp_c": 25},
        [{"mode": "cruise", "speed_kmh": 200, "duration_s": 480},
         {"mode": "brake", "speed_kmh": 100, "rate_g": 0.7, "duration_s": 5},
         {"mode": "full_throttle", "duration_s": 25},
         {"mode": "cruise", "speed_kmh": 200, "duration_s": 480},
         {"mode": "brake", "speed_kmh": 120, "rate_g": 0.6, "duration_s": 4},
         {"mode": "full_throttle", "duration_s": 20},
         {"mode": "cruise", "speed_kmh": 200, "duration_s": 180}], initial=200, dt=0.2),
    "towing_grade": _sc(
        "Long climb at speed, 6 %", "Twenty minutes up a 6 % motorway grade at 100 km/h in the heat: the cooling-system test.",
        {"ambient_temp_c": 38, "altitude_m": 800},
        [{"mode": "cruise", "speed_kmh": 100, "duration_s": 1200, "grade_pct": 6}], initial=100, dt=0.5),
    "alpine_descent": _sc(
        "Alpine descent on the brakes", "Ten minutes down a 10 % pass with hairpins: repeated braking from 90 to 30 km/h.",
        {"ambient_temp_c": 20, "altitude_m": 2000},
        [{"mode": "cruise", "speed_kmh": 90, "duration_s": 15, "grade_pct": -10},
         {"mode": "brake", "speed_kmh": 30, "rate_g": 0.5, "duration_s": 6, "grade_pct": -10},
         {"mode": "cruise", "speed_kmh": 30, "duration_s": 8, "grade_pct": -10},
         {"mode": "accelerate", "speed_kmh": 90, "rate_g": 0.25, "duration_s": 9, "grade_pct": -10}],
        repeats=16, initial=90, dt=0.1),
    "drag_strip": _sc(
        "Drag-strip evening", "Eight standing-start runs to the end of a 400 m strip, with return roads and cool-down.",
        {"ambient_temp_c": 24},
        [{"mode": "full_throttle", "duration_s": 13},
         {"mode": "brake", "speed_kmh": 30, "rate_g": 0.6, "duration_s": 8},
         {"mode": "cruise", "speed_kmh": 30, "duration_s": 60},
         {"mode": "brake", "speed_kmh": 0, "rate_g": 0.2, "duration_s": 5},
         {"mode": "idle", "duration_s": 240}], repeats=8, dt=0.1),
    "winter_commute": _sc(
        "Winter commute, −15 °C", "Cold start on snow: suburban roads then a short dual carriageway.",
        {"ambient_temp_c": -15, "surface": "snow"},
        [{"mode": "idle", "duration_s": 60},
         {"mode": "accelerate", "speed_kmh": 50, "rate_g": 0.08, "duration_s": 18},
         {"mode": "cruise", "speed_kmh": 50, "duration_s": 300},
         {"mode": "accelerate", "speed_kmh": 90, "rate_g": 0.08, "duration_s": 15},
         {"mode": "cruise", "speed_kmh": 90, "duration_s": 600},
         {"mode": "brake", "speed_kmh": 0, "rate_g": 0.1, "duration_s": 26}], dt=0.5),
    "desert_highway": _sc(
        "Desert highway, 48 °C", "An hour at 120 km/h through extreme heat with a long gentle climb.",
        {"ambient_temp_c": 48, "altitude_m": 300},
        [{"mode": "cruise", "speed_kmh": 120, "duration_s": 1800},
         {"mode": "cruise", "speed_kmh": 120, "duration_s": 900, "grade_pct": 3},
         {"mode": "cruise", "speed_kmh": 120, "duration_s": 900}], initial=120, dt=0.5),
    "endurance_stint": _sc(
        "Endurance stint", "Forty minutes of race pace: long straights, a heavy stop, fast sweepers.",
        {"ambient_temp_c": 30},
        [{"mode": "full_throttle", "duration_s": 16},
         {"mode": "brake", "speed_kmh": 80, "rate_g": 1.1, "duration_s": 5},
         {"mode": "cruise", "speed_kmh": 80, "duration_s": 5},
         {"mode": "full_throttle", "duration_s": 8},
         {"mode": "brake", "speed_kmh": 130, "rate_g": 0.8, "duration_s": 3},
         {"mode": "cruise", "speed_kmh": 130, "duration_s": 12},
         {"mode": "full_throttle", "duration_s": 10},
         {"mode": "brake", "speed_kmh": 60, "rate_g": 1.0, "duration_s": 5},
         {"mode": "cruise", "speed_kmh": 60, "duration_s": 6}], repeats=34, initial=80, dt=0.1),
}
