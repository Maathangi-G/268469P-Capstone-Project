"""Small FICTIONAL scheduling scenario builder for tests (no company data)."""

from __future__ import annotations

import copy
import csv
import json
from collections.abc import Callable
from pathlib import Path

from agriflight.scheduling.contracts import REQUIRED_FILES

DAY1, DAY2 = "2031-01-06", "2031-01-07"
P = "fictional test fixture"

BASE_META = {
    "scenario_id": "TEST_SCENARIO", "data_origin": "synthetic_demo", "timezone": "Asia/Colombo",
    "horizon_start": DAY1, "horizon_end": DAY2, "capacity_mode": "declared_assumption",
    "working_day": {"start": "08:00", "end": "16:00", "break_minutes": 30, "break_after_minutes": 240},
    "cadence": {"target_interval_days": 30, "operational_tolerance_days": 5, "proposal_tolerance_days": 3},
    "constraints_included": ["test"], "constraints_excluded": ["overnight stays"],
    "cost_categories_included": ["trip", "vehicle_day", "distance_km", "fuel_km", "personnel_person_day",
                                 "allowance_person_day"],
    "provenance": P,
}


def _job(job_id, site, area="60", due=DAY1, equipment="rgb_drone", skills="rgb", **extra):
    row = {"job_id": job_id, "division_id": f"DIV_{job_id}", "location_id": site, "required_area_ha": area,
           "planning_due_date": due, "preferred_window_start": DAY1, "preferred_window_end": DAY2,
           "required_equipment_type": equipment, "required_skills": skills, "input_status": "assumption",
           "provenance": P}
    row.update(extra)
    return row


LOCATIONS = ["D1", "D2", "S1", "S2", "S3", "S4"]

BASE_ROWS = {
    "jobs.csv": [_job("J1", "S1"), _job("J2", "S2", equipment="ms_drone", skills="ms")],
    "bundles.csv": [
        {"bundle_id": "B1", "depot_location_id": "D1", "pilot_ids": "P1", "vehicle_id": "V1", "equipment_ids": "E1",
         "work_rate_ha_per_hour": "60", "setup_min": "10", "input_status": "assumption", "provenance": P},
        {"bundle_id": "B2", "depot_location_id": "D2", "pilot_ids": "P2", "vehicle_id": "V2", "equipment_ids": "E2",
         "work_rate_ha_per_hour": "60", "setup_min": "10", "input_status": "assumption", "provenance": P},
    ],
    "pilots.csv": [{"pilot_id": "P1", "skills": "rgb", "input_status": "assumption", "provenance": P},
                   {"pilot_id": "P2", "skills": "rgb|ms", "input_status": "assumption", "provenance": P}],
    "vehicles.csv": [{"vehicle_id": "V1", "vehicle_type": "car", "input_status": "assumption", "provenance": P},
                     {"vehicle_id": "V2", "vehicle_type": "4wd", "input_status": "assumption", "provenance": P}],
    "equipment.csv": [{"equipment_id": "E1", "equipment_type": "rgb_drone", "input_status": "assumption", "provenance": P},
                      {"equipment_id": "E2", "equipment_type": "ms_drone", "input_status": "assumption", "provenance": P}],
    "availability.csv": [{"resource_type": t, "resource_id": r, "date": d, "available": "True", "provenance": P}
                         for t, ids in (("pilot", ["P1", "P2"]), ("vehicle", ["V1", "V2"]), ("equipment", ["E1", "E2"]))
                         for r in ids for d in (DAY1, DAY2)],
    "locations.csv": [{"location_id": loc, "location_kind": "depot" if loc.startswith("D") else "job_site",
                       "access_point_verified": "False", "provenance": P} for loc in LOCATIONS],
    "travel.csv": [{"from_location_id": a, "to_location_id": b, "travel_minutes": "30", "distance_km": "20",
                    "source": "fixture", "provenance": P} for a in LOCATIONS for b in LOCATIONS if a != b],
    "cost_rates.csv": [
        {"rate_id": "R_TRIP", "category": "trip", "applies_to": "*", "amount_lkr": "100", "input_status": "assumption", "provenance": P},
        {"rate_id": "R_VD_CAR", "category": "vehicle_day", "applies_to": "car", "amount_lkr": "1000", "includes_fuel": "False", "input_status": "assumption", "provenance": P},
        {"rate_id": "R_VD_4WD", "category": "vehicle_day", "applies_to": "4wd", "amount_lkr": "2000", "includes_fuel": "False", "input_status": "assumption", "provenance": P},
        {"rate_id": "R_KM_CAR", "category": "distance_km", "applies_to": "car", "amount_lkr": "10", "includes_fuel": "True", "input_status": "assumption", "provenance": P},
        {"rate_id": "R_KM_4WD", "category": "distance_km", "applies_to": "4wd", "amount_lkr": "5", "includes_fuel": "False", "input_status": "assumption", "provenance": P},
        {"rate_id": "R_FUEL_4WD", "category": "fuel_km", "applies_to": "4wd", "amount_lkr": "3", "input_status": "assumption", "provenance": P},
        {"rate_id": "R_PERSON", "category": "personnel_person_day", "applies_to": "*", "amount_lkr": "500", "input_status": "assumption", "provenance": P},
        {"rate_id": "R_ALLOW", "category": "allowance_person_day", "applies_to": "*", "amount_lkr": "50", "input_status": "assumption", "provenance": P},
    ],
}

Mutator = Callable[[dict, dict], None]


def job(job_id, site, **kwargs):
    return _job(job_id, site, **kwargs)


def build_scenario(root: Path, mutate: Mutator | None = None, drop: tuple[str, ...] = ()) -> Path:
    folder = root / "scenario"
    folder.mkdir(parents=True, exist_ok=True)
    meta, rows = copy.deepcopy(BASE_META), copy.deepcopy(BASE_ROWS)
    if mutate:
        mutate(meta, rows)
    if "scenario.json" not in drop:
        (folder / "scenario.json").write_text(json.dumps(meta), encoding="utf-8")
    for name, columns in REQUIRED_FILES.items():
        if name in drop:
            continue
        with (folder / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            for row in rows.get(name, []):
                writer.writerow({c: row.get(c, "") for c in columns})
    return folder


def set_travel(rows: dict, origin: str, destination: str, minutes: str | None, km: str = "20") -> None:
    rows["travel.csv"] = [t for t in rows["travel.csv"]
                          if (t["from_location_id"], t["to_location_id"]) != (origin, destination)]
    if minutes is not None:
        rows["travel.csv"].append({"from_location_id": origin, "to_location_id": destination,
                                   "travel_minutes": minutes, "distance_km": km, "source": "fixture", "provenance": P})


def set_available(rows: dict, resource_id: str, day: str, value: str | None) -> None:
    rows["availability.csv"] = [a for a in rows["availability.csv"]
                                if (a["resource_id"], a["date"]) != (resource_id, day)]
    if value is not None:
        rtype = {"P": "pilot", "V": "vehicle", "E": "equipment"}[resource_id[0]]
        rows["availability.csv"].append({"resource_type": rtype, "resource_id": resource_id, "date": day,
                                         "available": value, "provenance": P})
