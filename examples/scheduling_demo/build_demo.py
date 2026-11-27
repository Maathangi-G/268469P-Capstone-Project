"""Regenerate the FICTIONAL scheduling demo scenario in this folder.

Everything here is invented for demonstration and testing. Locations sit on
an abstract coordinate plane (kilometres from an arbitrary origin) that does
not correspond to any real place; work rates, availability and cost rates are
made-up assumptions. Nothing is derived from company records.

Run:  python examples/scheduling_demo/build_demo.py
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROV = "fictional demo (examples/scheduling_demo/build_demo.py)"
DAYS = ["2030-03-04", "2030-03-05", "2030-03-06"]

# Abstract plane (km); not real geography.
POINTS = {
    "DEPOT_NORTH": (0, 0), "DEPOT_SOUTH": (0, -40),
    "SITE_01": (10, 5), "SITE_02": (5, -35), "SITE_03": (20, 10), "SITE_04": (-8, -30),
    "SITE_05": (15, -5), "SITE_06": (-20, -50), "SITE_07": (0, -200), "SITE_08": (12, -20),
    "SITE_09": (25, 0), "SITE_10": (10, -45), "SITE_11": (-10, 8),
}

JOBS = [
    # job, division, site, area_ha, duration_min, setup, due, pref_start, pref_end, hard_from, hard_to, blocked,
    # access_start, access_end, vehicle, equipment, skills, note
    ("JOB_01", "DIV_DEMO_01", "SITE_01", "120", "", "", "2030-03-04", "2030-03-01", "2030-03-07", "", "", "", "", "",
     "4wd_pickup", "multispectral_drone", "multispectral"),
    ("JOB_02", "DIV_DEMO_02", "SITE_02", "60", "", "", "2030-03-04", "2030-03-01", "2030-03-07", "", "", "", "", "",
     "", "rgb_drone", "rgb"),
    ("JOB_03", "DIV_DEMO_03", "SITE_03", "90", "", "", "2030-03-05", "2030-03-02", "2030-03-08", "", "", "", "", "",
     "4wd_pickup", "multispectral_drone", "multispectral"),
    ("JOB_04", "DIV_DEMO_04", "SITE_04", "45", "", "", "2030-03-05", "2030-03-02", "2030-03-08", "", "", "",
     "09:00", "12:00", "", "rgb_drone", "rgb"),
    ("JOB_05", "DIV_DEMO_05", "SITE_05", "1200", "", "", "2030-03-05", "2030-03-02", "2030-03-08", "", "", "", "", "",
     "", "multispectral_drone", "multispectral"),
    ("JOB_06", "DIV_DEMO_06", "SITE_06", "50", "", "", "2030-03-05", "2030-03-02", "2030-03-08", "", "", "", "", "",
     "", "rgb_drone", "rgb"),
    ("JOB_07", "DIV_DEMO_07", "SITE_07", "135", "", "", "2030-03-05", "2030-03-02", "2030-03-08", "", "", "", "", "",
     "", "rgb_drone", "rgb"),
    ("JOB_08", "DIV_DEMO_08", "SITE_08", "40", "", "", "2030-03-05", "2030-03-02", "2030-03-08", "", "", "", "", "",
     "", "thermal_camera", "thermal"),
    ("JOB_09", "DIV_DEMO_09", "SITE_09", "70", "", "", "2030-03-02", "2030-02-28", "2030-03-04", "2030-03-06",
     "2030-03-06", "", "", "", "", "multispectral_drone", "multispectral"),
    ("JOB_10", "DIV_DEMO_02", "SITE_10", "", "120", "10", "2030-03-05", "2030-03-02", "2030-03-08", "", "",
     "2030-03-04", "", "", "", "rgb_drone", "rgb"),
    ("JOB_11", "DIV_DEMO_10", "SITE_11", "70", "", "", "2030-03-05", "2030-03-02", "2030-03-08", "", "", "", "", "",
     "", "multispectral_drone", "multispectral"),
]


def km_between(a: str, b: str) -> float:
    (x1, y1), (x2, y2) = POINTS[a], POINTS[b]
    return round(math.hypot(x2 - x1, y2 - y1) * 1.25, 1)  # fictional road factor


def write(name: str, header: list[str], rows: list[list]) -> None:
    with (HERE / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    scenario = {
        "scenario_id": "DEMO_SCHEDULING_V1",
        "data_origin": "synthetic_demo",
        "timezone": "Asia/Colombo",
        "horizon_start": DAYS[0], "horizon_end": DAYS[-1],
        "capacity_mode": "declared_assumption",
        "working_day": {"start": "07:00", "end": "17:00", "break_minutes": 30, "break_after_minutes": 300},
        "cadence": {"target_interval_days": 30, "operational_tolerance_days": 5, "proposal_tolerance_days": 3,
                    "preferred_windows": "soft; reported, never used to exclude a job"},
        "constraints_included": ["resource availability", "no shared physical resource across bundles per day",
                                 "vehicle/equipment/skill compatibility", "hard booking dates and blocked dates",
                                 "daily access windows", "directed travel matrix (missing = no route)",
                                 "working day incl. break and return to depot"],
        "constraints_excluded": ["overnight stays", "job splitting / multi-day jobs", "weather and flying restrictions",
                                 "battery and charging limits", "fuel tank range", "pilot duty-hour regulations"],
        "cost_categories_included": ["trip", "vehicle_day", "distance_km", "fuel_km", "personnel_person_day",
                                     "allowance_person_day"],
        "provenance": PROV,
        "notes": "Entirely fictional demonstration scenario. Not company data; not an approved planning input.",
    }
    (HERE / "scenario.json").write_text(json.dumps(scenario, indent=2) + "\n", encoding="utf-8")

    write("jobs.csv", ["job_id", "division_id", "location_id", "required_area_ha", "service_duration_min", "setup_min",
                       "planning_due_date", "preferred_window_start", "preferred_window_end", "hard_earliest_date",
                       "hard_latest_date", "blocked_dates", "access_start", "access_end", "required_vehicle_type",
                       "required_equipment_type", "required_skills", "input_status", "provenance"],
          [list(j) + ["assumption", PROV] for j in JOBS])
    write("pilots.csv", ["pilot_id", "skills", "input_status", "provenance"],
          [["PIL_A1", "multispectral|rgb", "assumption", PROV], ["PIL_A2", "rgb", "assumption", PROV],
           ["PIL_B1", "rgb", "assumption", PROV], ["PIL_C1", "multispectral|rgb", "assumption", PROV]])
    write("vehicles.csv", ["vehicle_id", "vehicle_type", "input_status", "provenance"],
          [["VEH_4WD_1", "4wd_pickup", "assumption", PROV], ["VEH_CAR_1", "car", "assumption", PROV],
           ["VEH_CAR_2", "car", "assumption", PROV]])
    write("equipment.csv", ["equipment_id", "equipment_type", "input_status", "provenance"],
          [["DRN_MS_1", "multispectral_drone", "assumption", PROV], ["DRN_RGB_1", "rgb_drone", "assumption", PROV]])
    # TEAM_C shares the multispectral drone with TEAM_A (shared-resource case).
    write("bundles.csv", ["bundle_id", "depot_location_id", "pilot_ids", "vehicle_id", "equipment_ids",
                          "work_rate_ha_per_hour", "setup_min", "input_status", "provenance"],
          [["TEAM_A", "DEPOT_NORTH", "PIL_A1|PIL_A2", "VEH_4WD_1", "DRN_MS_1", "40", "20", "assumption", PROV],
           ["TEAM_B", "DEPOT_SOUTH", "PIL_B1", "VEH_CAR_1", "DRN_RGB_1", "30", "15", "assumption", PROV],
           ["TEAM_C", "DEPOT_NORTH", "PIL_C1", "VEH_CAR_2", "DRN_MS_1", "35", "20", "assumption", PROV]])
    avail = []
    for rtype, ids in (("pilot", ["PIL_A1", "PIL_A2", "PIL_B1", "PIL_C1"]), ("vehicle", ["VEH_4WD_1", "VEH_CAR_1",
                       "VEH_CAR_2"]), ("equipment", ["DRN_MS_1", "DRN_RGB_1"])):
        for rid in ids:
            for day in DAYS:
                ok = not (rid == "PIL_A2" and day == "2030-03-05")  # pilot unavailable on day 2
                avail.append([rtype, rid, day, "True" if ok else "False", PROV])
    write("availability.csv", ["resource_type", "resource_id", "date", "available", "provenance"], avail)
    write("locations.csv", ["location_id", "location_kind", "access_point_verified", "provenance"],
          [[loc, "depot" if loc.startswith("DEPOT") else "job_site", "False", PROV] for loc in POINTS])

    travel = []
    names = sorted(POINTS)
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if a == b:
                continue
            if "SITE_06" in (a, b) and (a, b) != ("DEPOT_SOUTH", "SITE_06"):
                continue  # missing connections: only DEPOT_SOUTH -> SITE_06 exists
            km = km_between(a, b)
            minutes = round(km * 1.1 + 8) + (6 if (i + j) % 2 and i < j else 0)  # deliberate asymmetry
            travel.append([a, b, minutes, km, "fictional_planar_estimate", PROV])
    write("travel.csv", ["from_location_id", "to_location_id", "travel_minutes", "distance_km", "source", "provenance"],
          travel)
    write("cost_rates.csv", ["rate_id", "category", "applies_to", "amount_lkr", "includes_fuel", "input_status",
                             "provenance"],
          [["RATE_TRIP", "trip", "*", "500", "", "assumption", PROV],
           ["RATE_VDAY_4WD", "vehicle_day", "4wd_pickup", "18000", "False", "assumption", PROV],
           ["RATE_VDAY_CAR", "vehicle_day", "car", "9000", "False", "assumption", PROV],
           ["RATE_KM_4WD", "distance_km", "4wd_pickup", "40", "False", "assumption", PROV],
           ["RATE_KM_CAR_ALLIN", "distance_km", "car", "60", "True", "assumption", PROV],
           ["RATE_FUEL_4WD", "fuel_km", "4wd_pickup", "55", "", "assumption", PROV],
           ["RATE_PERSON_DAY", "personnel_person_day", "*", "7500", "", "assumption", PROV],
           ["RATE_ALLOWANCE", "allowance_person_day", "*", "", "", "assumption", PROV]])


if __name__ == "__main__":
    main()
