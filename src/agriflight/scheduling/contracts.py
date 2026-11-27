"""Planning-input contracts for the rule-based scheduling baseline.

A scenario is a folder of small CSV files plus ``scenario.json``. Every input
row carries provenance and an input status (approved / assumption). Nothing
is inferred: a missing travel entry is a missing route (never zero travel), a
missing availability row means the resource is NOT available, and a blank cost
rate is an unknown cost (never zero).

Times are local Asia/Colombo wall-clock times (HH:MM); dates are YYYY-MM-DD.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

TIMEZONE = "Asia/Colombo"
CAPACITY_MODE = "declared_assumption"
SYNTHETIC_ORIGIN = "synthetic_demo"
INPUT_STATUSES = ("approved", "assumption")
RESOURCE_TYPES = ("pilot", "vehicle", "equipment")
COST_CATEGORIES = ("vehicle_day", "distance_km", "fuel_km", "personnel_person_day", "allowance_person_day", "trip")

REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "jobs.csv": ("job_id", "division_id", "location_id", "required_area_ha", "service_duration_min", "setup_min",
                 "planning_due_date", "preferred_window_start", "preferred_window_end", "hard_earliest_date",
                 "hard_latest_date", "blocked_dates", "access_start", "access_end", "required_vehicle_type",
                 "required_equipment_type", "required_skills", "input_status", "provenance"),
    "bundles.csv": ("bundle_id", "depot_location_id", "pilot_ids", "vehicle_id", "equipment_ids",
                    "work_rate_ha_per_hour", "setup_min", "input_status", "provenance"),
    "pilots.csv": ("pilot_id", "skills", "input_status", "provenance"),
    "vehicles.csv": ("vehicle_id", "vehicle_type", "input_status", "provenance"),
    "equipment.csv": ("equipment_id", "equipment_type", "input_status", "provenance"),
    "availability.csv": ("resource_type", "resource_id", "date", "available", "provenance"),
    "locations.csv": ("location_id", "location_kind", "access_point_verified", "provenance"),
    "travel.csv": ("from_location_id", "to_location_id", "travel_minutes", "distance_km", "source", "provenance"),
    "cost_rates.csv": ("rate_id", "category", "applies_to", "amount_lkr", "includes_fuel", "input_status", "provenance"),
}
REQUIRED_SCENARIO_KEYS = ("scenario_id", "data_origin", "timezone", "horizon_start", "horizon_end", "capacity_mode",
                          "working_day", "cadence", "constraints_included", "constraints_excluded",
                          "cost_categories_included", "provenance")


class ScenarioError(ValueError):
    """The scenario lacks required inputs or has invalid values."""

    def __init__(self, issues: list[dict]):
        self.issues = issues
        errors = [i for i in issues if i["severity"] == "error"]
        super().__init__(f"{len(errors)} scenario input error(s): " +
                         "; ".join(f"{i['file']} {i['record_id']} {i['field']}: {i['message']}" for i in errors[:5]))


@dataclass(frozen=True)
class Job:
    job_id: str
    division_id: str
    location_id: str
    required_area_ha: float | None
    service_duration_min: float | None
    setup_min: float | None
    planning_due_date: date
    preferred_window_start: date
    preferred_window_end: date
    hard_earliest_date: date | None
    hard_latest_date: date | None
    blocked_dates: frozenset[date]
    access_start_min: int | None
    access_end_min: int | None
    required_vehicle_type: str | None
    required_equipment_type: str | None
    required_skills: frozenset[str]
    input_status: str
    provenance: str


@dataclass(frozen=True)
class Bundle:
    bundle_id: str
    depot_location_id: str
    pilot_ids: tuple[str, ...]
    vehicle_id: str
    equipment_ids: tuple[str, ...]
    work_rate_ha_per_hour: float | None
    setup_min: float
    input_status: str
    provenance: str

    @property
    def resources(self) -> tuple[tuple[str, str], ...]:
        return (tuple(("pilot", p) for p in self.pilot_ids) + (("vehicle", self.vehicle_id),)
                + tuple(("equipment", e) for e in self.equipment_ids))


@dataclass(frozen=True)
class Leg:
    travel_minutes: float
    distance_km: float | None
    source: str


@dataclass(frozen=True)
class CostRate:
    rate_id: str
    category: str
    applies_to: str
    amount_lkr: float | None
    includes_fuel: bool
    input_status: str
    provenance: str


@dataclass
class Scenario:
    scenario_id: str
    data_origin: str
    horizon: list[date]
    day_start_min: int
    day_end_min: int
    break_minutes: int
    break_after_minutes: int
    cadence: dict
    constraints_included: list[str]
    constraints_excluded: list[str]
    cost_categories_included: list[str]
    provenance: str
    jobs: dict[str, Job]
    bundles: list[Bundle]
    pilot_skills: dict[str, frozenset[str]]
    vehicle_types: dict[str, str]
    equipment_types: dict[str, str]
    availability: dict[tuple[str, str, date], bool]
    locations: dict[str, dict]
    travel: dict[tuple[str, str], Leg]
    cost_rates: list[CostRate]
    notes: str = ""
    issues: list[dict] = field(default_factory=list)

    @property
    def is_synthetic(self) -> bool:
        return self.data_origin == SYNTHETIC_ORIGIN

    def leg(self, origin: str, destination: str) -> Leg | None:
        return self.travel.get((origin, destination))

    def available(self, resource_type: str, resource_id: str, day: date) -> bool:
        return self.availability.get((resource_type, resource_id, day), False)

    def bundle_capabilities(self, bundle: Bundle) -> tuple[str | None, set[str], set[str]]:
        skills: set[str] = set()
        for p in bundle.pilot_ids:
            skills |= set(self.pilot_skills.get(p, frozenset()))
        return (self.vehicle_types.get(bundle.vehicle_id),
                {self.equipment_types[e] for e in bundle.equipment_ids if e in self.equipment_types}, skills)


# ------------------------------------------------------------------ parsing
def parse_hhmm(text: str) -> int:
    hours, minutes = text.strip().split(":")
    value = int(hours) * 60 + int(minutes)
    if not 0 <= value <= 24 * 60:
        raise ValueError(text)
    return value


def format_hhmm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def _split(text: str) -> list[str]:
    return [p.strip() for p in str(text).split("|") if p.strip()]


class _Collector:
    def __init__(self) -> None:
        self.issues: list[dict] = []

    def add(self, severity: str, file: str, record_id: str, column: str, message: str) -> None:
        self.issues.append({"severity": severity, "file": file, "record_id": record_id, "field": column,
                            "message": message})

    def date(self, file, rid, column, text, required=True) -> date | None:
        text = str(text).strip()
        if not text:
            if required:
                self.add("error", file, rid, column, "required date is blank")
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            self.add("error", file, rid, column, f"not a YYYY-MM-DD date: {text!r}")
            return None

    def number(self, file, rid, column, text, required=False, positive=False) -> float | None:
        text = str(text).strip()
        if not text:
            if required:
                self.add("error", file, rid, column, "required number is blank")
            return None
        try:
            value = float(text)
        except ValueError:
            self.add("error", file, rid, column, f"not a number: {text!r}")
            return None
        if not math.isfinite(value) or value < 0 or (positive and value == 0):
            self.add("error", file, rid, column, f"must be a finite {'positive' if positive else 'non-negative'} number")
            return None
        return value

    def boolean(self, file, rid, column, text, required=True) -> bool | None:
        text = str(text).strip()
        if text in ("True", "False"):
            return text == "True"
        if text or required:
            self.add("error", file, rid, column, f"must be the text True or False, got {text!r}")
        return None

    def time(self, file, rid, column, text) -> int | None:
        text = str(text).strip()
        if not text:
            return None
        try:
            return parse_hhmm(text)
        except (ValueError, IndexError):
            self.add("error", file, rid, column, f"not an HH:MM time: {text!r}")
            return None

    def status(self, file, rid, text) -> str:
        text = str(text).strip()
        if text not in INPUT_STATUSES:
            self.add("error", file, rid, "input_status", f"must be one of {INPUT_STATUSES}")
        return text


def _read(folder: Path, name: str, c: _Collector) -> pd.DataFrame | None:
    path = folder / name
    if not path.exists():
        c.add("error", name, "", "", "required input file is missing")
        return None
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig")
    missing = [col for col in REQUIRED_FILES[name] if col not in frame.columns]
    for col in missing:
        c.add("error", name, "", col, "required column is missing")
    if missing:
        return None
    for key in frame.columns[:1]:
        dupes = frame[key][frame[key].duplicated() & (frame[key] != "")]
        if name not in ("availability.csv", "travel.csv") and not dupes.empty:
            c.add("error", name, ", ".join(sorted(set(dupes))[:5]), key, "duplicate identifier")
        if name not in ("availability.csv", "travel.csv") and (frame[key].str.strip() == "").any():
            c.add("error", name, "", key, "blank identifier")
    return frame


def load_scenario(folder: Path) -> Scenario:
    """Load and validate a scenario folder. Raises ScenarioError listing every missing/invalid input."""
    folder = Path(folder)
    c = _Collector()
    meta: dict = {}
    if not (folder / "scenario.json").exists():
        c.add("error", "scenario.json", "", "", "required input file is missing")
    else:
        try:
            meta = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            c.add("error", "scenario.json", "", "", f"invalid JSON: {exc}")
    for key in REQUIRED_SCENARIO_KEYS:
        if key not in meta:
            c.add("error", "scenario.json", "", key, "required scenario setting is missing")
    frames = {name: _read(folder, name, c) for name in REQUIRED_FILES}
    if any(i["severity"] == "error" for i in c.issues):
        raise ScenarioError(c.issues)

    if meta["timezone"] != TIMEZONE:
        c.add("error", "scenario.json", "", "timezone", f"must be {TIMEZONE}")
    if meta["capacity_mode"] != CAPACITY_MODE:
        c.add("error", "scenario.json", "", "capacity_mode", f"must be {CAPACITY_MODE!r} (no ML capacity in this baseline)")
    start = c.date("scenario.json", "", "horizon_start", meta["horizon_start"])
    end = c.date("scenario.json", "", "horizon_end", meta["horizon_end"])
    horizon = [start + timedelta(days=i) for i in range((end - start).days + 1)] if start and end and start <= end else []
    if start and end and start > end:
        c.add("error", "scenario.json", "", "horizon_end", "horizon_end is before horizon_start")
    wd = meta.get("working_day", {})
    day_start = c.time("scenario.json", "", "working_day.start", wd.get("start", ""))
    day_end = c.time("scenario.json", "", "working_day.end", wd.get("end", ""))
    if day_start is None or day_end is None or day_end <= day_start:
        c.add("error", "scenario.json", "", "working_day", "start and end (HH:MM) are required and end must be after start")
    break_minutes = c.number("scenario.json", "", "working_day.break_minutes", wd.get("break_minutes", ""), required=True)
    break_after = c.number("scenario.json", "", "working_day.break_after_minutes", wd.get("break_after_minutes", ""), required=True)
    for cat in meta.get("cost_categories_included", []):
        if cat not in COST_CATEGORIES:
            c.add("error", "scenario.json", "", "cost_categories_included", f"unsupported category {cat!r}")

    locations = {}
    for _, r in frames["locations.csv"].iterrows():
        verified = c.boolean("locations.csv", r["location_id"], "access_point_verified", r["access_point_verified"])
        locations[r["location_id"]] = {"kind": r["location_kind"], "access_point_verified": verified,
                                       "provenance": r["provenance"]}

    pilot_skills = {r["pilot_id"]: frozenset(_split(r["skills"])) for _, r in frames["pilots.csv"].iterrows()}
    for _, r in frames["pilots.csv"].iterrows():
        c.status("pilots.csv", r["pilot_id"], r["input_status"])
    vehicle_types = {r["vehicle_id"]: r["vehicle_type"].strip() for _, r in frames["vehicles.csv"].iterrows()}
    equipment_types = {r["equipment_id"]: r["equipment_type"].strip() for _, r in frames["equipment.csv"].iterrows()}

    bundles = []
    for _, r in frames["bundles.csv"].iterrows():
        bid = r["bundle_id"]
        pilots, equipment = tuple(_split(r["pilot_ids"])), tuple(_split(r["equipment_ids"]))
        if not pilots:
            c.add("error", "bundles.csv", bid, "pilot_ids", "a bundle needs at least one pilot")
        for p in pilots:
            if p not in pilot_skills:
                c.add("error", "bundles.csv", bid, "pilot_ids", f"unknown pilot {p}")
        if r["vehicle_id"] not in vehicle_types:
            c.add("error", "bundles.csv", bid, "vehicle_id", f"unknown vehicle {r['vehicle_id']}")
        for e in equipment:
            if e not in equipment_types:
                c.add("error", "bundles.csv", bid, "equipment_ids", f"unknown equipment {e}")
        if r["depot_location_id"] not in locations:
            c.add("error", "bundles.csv", bid, "depot_location_id", "unknown location")
        rate = c.number("bundles.csv", bid, "work_rate_ha_per_hour", r["work_rate_ha_per_hour"], positive=True)
        setup = c.number("bundles.csv", bid, "setup_min", r["setup_min"], required=True)
        bundles.append(Bundle(bid, r["depot_location_id"], pilots, r["vehicle_id"], equipment, rate, setup or 0.0,
                              c.status("bundles.csv", bid, r["input_status"]), r["provenance"]))
    bundles.sort(key=lambda b: b.bundle_id)

    jobs = {}
    for _, r in frames["jobs.csv"].iterrows():
        jid = r["job_id"]
        due = c.date("jobs.csv", jid, "planning_due_date", r["planning_due_date"])
        pstart = c.date("jobs.csv", jid, "preferred_window_start", r["preferred_window_start"])
        pend = c.date("jobs.csv", jid, "preferred_window_end", r["preferred_window_end"])
        if pstart and pend and pstart > pend:
            c.add("error", "jobs.csv", jid, "preferred_window_end", "preferred window ends before it starts")
        hard_from = c.date("jobs.csv", jid, "hard_earliest_date", r["hard_earliest_date"], required=False)
        hard_to = c.date("jobs.csv", jid, "hard_latest_date", r["hard_latest_date"], required=False)
        blocked = frozenset(d for d in (c.date("jobs.csv", jid, "blocked_dates", t) for t in _split(r["blocked_dates"])) if d)
        area = c.number("jobs.csv", jid, "required_area_ha", r["required_area_ha"])
        duration = c.number("jobs.csv", jid, "service_duration_min", r["service_duration_min"], positive=True)
        if area is None and duration is None:
            c.add("warning", "jobs.csv", jid, "required_area_ha", "neither area nor service duration supplied; "
                  "job cannot be scheduled by this baseline")
        if r["location_id"] not in locations:
            c.add("error", "jobs.csv", jid, "location_id", "unknown location")
        access_start = c.time("jobs.csv", jid, "access_start", r["access_start"])
        access_end = c.time("jobs.csv", jid, "access_end", r["access_end"])
        if access_start is not None and access_end is not None and access_end <= access_start:
            c.add("error", "jobs.csv", jid, "access_end", "access window ends before it starts")
        jobs[jid] = Job(jid, r["division_id"], r["location_id"], area, duration,
                        c.number("jobs.csv", jid, "setup_min", r["setup_min"]), due, pstart, pend,
                        hard_from, hard_to, blocked, access_start, access_end,
                        r["required_vehicle_type"].strip() or None, r["required_equipment_type"].strip() or None,
                        frozenset(_split(r["required_skills"])), c.status("jobs.csv", jid, r["input_status"]),
                        r["provenance"])

    known = {"pilot": set(pilot_skills), "vehicle": set(vehicle_types), "equipment": set(equipment_types)}
    availability: dict[tuple[str, str, date], bool] = {}
    for _, r in frames["availability.csv"].iterrows():
        rtype, rid = r["resource_type"].strip(), r["resource_id"].strip()
        if rtype not in RESOURCE_TYPES or rid not in known.get(rtype, set()):
            c.add("error", "availability.csv", rid, "resource_id", f"unknown {rtype or 'resource'}")
            continue
        day = c.date("availability.csv", rid, "date", r["date"])
        flag = c.boolean("availability.csv", rid, "available", r["available"])
        if day and flag is not None:
            if (rtype, rid, day) in availability:
                c.add("error", "availability.csv", rid, "date", f"duplicate availability row for {day}")
            availability[(rtype, rid, day)] = flag

    travel: dict[tuple[str, str], Leg] = {}
    for _, r in frames["travel.csv"].iterrows():
        key = (r["from_location_id"].strip(), r["to_location_id"].strip())
        rid = f"{key[0]}->{key[1]}"
        if key[0] not in locations or key[1] not in locations:
            c.add("error", "travel.csv", rid, "location", "unknown location")
            continue
        if key in travel:
            c.add("error", "travel.csv", rid, "", "duplicate directed travel entry")
        minutes = c.number("travel.csv", rid, "travel_minutes", r["travel_minutes"], required=True)
        km = c.number("travel.csv", rid, "distance_km", r["distance_km"])
        if minutes is not None:
            travel[key] = Leg(minutes, km, r["source"])

    rates = []
    for _, r in frames["cost_rates.csv"].iterrows():
        rid, cat = r["rate_id"], r["category"].strip()
        if cat not in COST_CATEGORIES:
            c.add("error", "cost_rates.csv", rid, "category", f"unsupported category {cat!r}")
            continue
        fuel = c.boolean("cost_rates.csv", rid, "includes_fuel", r["includes_fuel"], required=False)
        rates.append(CostRate(rid, cat, r["applies_to"].strip() or "*",
                              c.number("cost_rates.csv", rid, "amount_lkr", r["amount_lkr"]), bool(fuel),
                              c.status("cost_rates.csv", rid, r["input_status"]), r["provenance"]))
    keys = [(r.category, r.applies_to) for r in rates]
    for key in {k for k in keys if keys.count(k) > 1}:
        c.add("error", "cost_rates.csv", f"{key[0]}/{key[1]}", "category", "more than one rate for the same category and scope")

    cadence = meta["cadence"]
    for key in ("target_interval_days", "operational_tolerance_days", "proposal_tolerance_days"):
        if key not in cadence:
            c.add("error", "scenario.json", "", f"cadence.{key}", "required cadence setting is missing")

    if any(i["severity"] == "error" for i in c.issues):
        raise ScenarioError(c.issues)
    return Scenario(
        scenario_id=meta["scenario_id"], data_origin=meta["data_origin"], horizon=horizon,
        day_start_min=day_start, day_end_min=day_end, break_minutes=int(break_minutes),
        break_after_minutes=int(break_after), cadence=cadence,
        constraints_included=list(meta["constraints_included"]), constraints_excluded=list(meta["constraints_excluded"]),
        cost_categories_included=list(meta["cost_categories_included"]), provenance=meta["provenance"],
        jobs=jobs, bundles=bundles, pilot_skills=pilot_skills, vehicle_types=vehicle_types,
        equipment_types=equipment_types, availability=availability, locations=locations, travel=travel,
        cost_rates=rates, notes=meta.get("notes", ""), issues=c.issues,
    )
