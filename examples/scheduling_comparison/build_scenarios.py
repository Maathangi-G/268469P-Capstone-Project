"""Generate the FICTIONAL comparison scenarios (baseline vs CP-SAT optimizer).

All values are invented. Locations are abstract node names with made-up
directed travel times; nothing is derived from company records. The intent
of each scenario is recorded in README.md BEFORE any evaluation.

Run:  python examples/scheduling_comparison/build_scenarios.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROV = "fictional comparison scenario (examples/scheduling_comparison/build_scenarios.py)"
DAY1, DAY2 = "2030-06-03", "2030-06-04"
BEFORE = "2030-06-02"

COLUMNS = {
    "jobs.csv": ["job_id", "division_id", "location_id", "required_area_ha", "service_duration_min", "setup_min",
                 "planning_due_date", "preferred_window_start", "preferred_window_end", "hard_earliest_date",
                 "hard_latest_date", "blocked_dates", "access_start", "access_end", "required_vehicle_type",
                 "required_equipment_type", "required_skills", "input_status", "provenance"],
    "bundles.csv": ["bundle_id", "depot_location_id", "pilot_ids", "vehicle_id", "equipment_ids",
                    "work_rate_ha_per_hour", "setup_min", "input_status", "provenance"],
    "pilots.csv": ["pilot_id", "skills", "input_status", "provenance"],
    "vehicles.csv": ["vehicle_id", "vehicle_type", "input_status", "provenance"],
    "equipment.csv": ["equipment_id", "equipment_type", "input_status", "provenance"],
    "availability.csv": ["resource_type", "resource_id", "date", "available", "provenance"],
    "locations.csv": ["location_id", "location_kind", "access_point_verified", "provenance"],
    "travel.csv": ["from_location_id", "to_location_id", "travel_minutes", "distance_km", "source", "provenance"],
    "cost_rates.csv": ["rate_id", "category", "applies_to", "amount_lkr", "includes_fuel", "input_status", "provenance"],
}
RATES = [
    {"rate_id": "R_TRIP", "category": "trip", "applies_to": "*", "amount_lkr": "500"},
    {"rate_id": "R_VD_CAR", "category": "vehicle_day", "applies_to": "car", "amount_lkr": "9000", "includes_fuel": "False"},
    {"rate_id": "R_VD_4WD", "category": "vehicle_day", "applies_to": "4wd", "amount_lkr": "18000", "includes_fuel": "False"},
    {"rate_id": "R_KM_CAR", "category": "distance_km", "applies_to": "car", "amount_lkr": "60", "includes_fuel": "True"},
    {"rate_id": "R_KM_4WD", "category": "distance_km", "applies_to": "4wd", "amount_lkr": "40", "includes_fuel": "False"},
    {"rate_id": "R_FUEL_4WD", "category": "fuel_km", "applies_to": "4wd", "amount_lkr": "55"},
    {"rate_id": "R_PERSON", "category": "personnel_person_day", "applies_to": "*", "amount_lkr": "7500"},
    {"rate_id": "R_ALLOW", "category": "allowance_person_day", "applies_to": "*", "amount_lkr": ""},  # unknown on purpose
]


def job(jid, site, minutes=None, area=None, due=DAY1, win=(DAY1, DAY2), equipment="ms_drone", skills="ms", **extra):
    row = {"job_id": jid, "division_id": f"DIV_{jid}", "location_id": site,
           "required_area_ha": "" if area is None else str(area),
           "service_duration_min": "" if minutes is None else str(minutes), "setup_min": "0",
           "planning_due_date": due, "preferred_window_start": win[0], "preferred_window_end": win[1],
           "required_equipment_type": equipment, "required_skills": skills}
    row.update(extra)
    return row


def bundle(bid, depot, pilots, vehicle, equipment, rate="30"):
    return {"bundle_id": bid, "depot_location_id": depot, "pilot_ids": pilots, "vehicle_id": vehicle,
            "equipment_ids": equipment, "work_rate_ha_per_hour": rate, "setup_min": "0"}


def write(name: str, title: str, horizon: tuple[str, str], bundles, pilots, vehicles, equipment, jobs, travel,
          unavailable=()):
    folder = HERE / name
    folder.mkdir(exist_ok=True)
    days = [horizon[0]] if horizon[0] == horizon[1] else [horizon[0], horizon[1]]
    locations = sorted({b["depot_location_id"] for b in bundles} | {j["location_id"] for j in jobs}
                       | {t[0] for t in travel} | {t[1] for t in travel})
    meta = {
        "scenario_id": name.upper(), "data_origin": "synthetic_demo", "timezone": "Asia/Colombo",
        "horizon_start": horizon[0], "horizon_end": horizon[1], "capacity_mode": "declared_assumption",
        "working_day": {"start": "08:00", "end": "16:00", "break_minutes": 30, "break_after_minutes": 240},
        "cadence": {"target_interval_days": 30, "operational_tolerance_days": 5, "proposal_tolerance_days": 3},
        "constraints_included": ["same rule set as examples/scheduling_demo"],
        "constraints_excluded": ["overnight stays", "job splitting", "weather"],
        "cost_categories_included": ["trip", "vehicle_day", "distance_km", "fuel_km", "personnel_person_day",
                                     "allowance_person_day"],
        "provenance": PROV, "notes": f"FICTIONAL comparison scenario: {title}",
    }
    (folder / "scenario.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    resources = ([("pilot", p["pilot_id"]) for p in pilots] + [("vehicle", v["vehicle_id"]) for v in vehicles]
                 + [("equipment", e["equipment_id"]) for e in equipment])
    rows = {
        "jobs.csv": [{**j, "input_status": "assumption", "provenance": PROV} for j in jobs],
        "bundles.csv": [{**b, "input_status": "assumption", "provenance": PROV} for b in bundles],
        "pilots.csv": [{**p, "input_status": "assumption", "provenance": PROV} for p in pilots],
        "vehicles.csv": [{**v, "input_status": "assumption", "provenance": PROV} for v in vehicles],
        "equipment.csv": [{**e, "input_status": "assumption", "provenance": PROV} for e in equipment],
        "availability.csv": [{"resource_type": t, "resource_id": r, "date": d,
                              "available": "False" if (r, d) in unavailable else "True", "provenance": PROV}
                             for t, r in resources for d in days],
        "locations.csv": [{"location_id": loc, "location_kind": "depot" if loc.startswith("DEP") else "job_site",
                           "access_point_verified": "False", "provenance": PROV} for loc in locations],
        "travel.csv": [{"from_location_id": a, "to_location_id": b, "travel_minutes": str(m), "distance_km": str(km),
                        "source": "fictional", "provenance": PROV} for a, b, m, km in travel],
        "cost_rates.csv": [{**r, "input_status": "assumption", "provenance": PROV} for r in RATES],
    }
    for file, cols in COLUMNS.items():
        with (folder / file).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=cols, lineterminator="\n")
            writer.writeheader()
            for row in rows[file]:
                writer.writerow({c: row.get(c, "") for c in cols})


def full(nodes, minutes=30, km=20):
    return [(a, b, minutes, km) for a in nodes for b in nodes if a != b]


PIL = [{"pilot_id": "PIL_1", "skills": "ms"}, {"pilot_id": "PIL_2", "skills": "ms"}]
CAR = {"vehicle_id": "VEH_CAR", "vehicle_type": "car"}
FWD = {"vehicle_id": "VEH_4WD", "vehicle_type": "4wd"}
DR1 = {"equipment_id": "DRN_1", "equipment_type": "ms_drone"}
DR2 = {"equipment_id": "DRN_2", "equipment_type": "ms_drone"}


def main() -> None:
    # C1 - tiny, manually solvable: two jobs, one team, asymmetric travel.
    # Optimum (by hand): both jobs, 0 window days, route DEP->A->B->DEP = 10+10+10 = 30 min.
    write("c1_tiny_manual", "tiny manually solvable case", (DAY1, DAY1),
          [bundle("TEAM_1", "DEP_1", "PIL_1", "VEH_CAR", "DRN_1")], PIL[:1], [CAR], [DR1],
          [job("JA", "SITE_A", minutes=60), job("JB", "SITE_B", minutes=60, due=BEFORE)],
          [("DEP_1", "SITE_A", 10, 10), ("SITE_A", "SITE_B", 10, 10), ("SITE_B", "DEP_1", 10, 10),
           ("DEP_1", "SITE_B", 20, 20), ("SITE_B", "SITE_A", 20, 20), ("SITE_A", "DEP_1", 20, 20)])
    # C2 - baseline already performs well: two independent teams, two nearby jobs each.
    write("c2_baseline_good", "independent teams; greedy expected to do well", (DAY1, DAY1),
          [bundle("TEAM_1", "DEP_1", "PIL_1", "VEH_CAR", "DRN_1"), bundle("TEAM_2", "DEP_2", "PIL_2", "VEH_4WD", "DRN_2")],
          PIL, [CAR, FWD], [DR1, DR2],
          [job("J1", "SITE_1", minutes=90), job("J2", "SITE_2", minutes=90, due=BEFORE),
           job("J3", "SITE_3", minutes=90, required_vehicle_type="4wd"),
           job("J4", "SITE_4", minutes=90, due=BEFORE, required_vehicle_type="4wd")],
          [(a, b, 20, 15) for a in ("DEP_1", "SITE_1", "SITE_2") for b in ("DEP_1", "SITE_1", "SITE_2") if a != b]
          + [(a, b, 20, 15) for a in ("DEP_2", "SITE_3", "SITE_4") for b in ("DEP_2", "SITE_3", "SITE_4") if a != b])
    # C3 - competition for a shared drone: TEAM_1 (car) and TEAM_2 (4wd) share DRN_1.
    write("c3_shared_resource", "two bundles share one drone", (DAY1, DAY1),
          [bundle("TEAM_1", "DEP_1", "PIL_1", "VEH_CAR", "DRN_1"), bundle("TEAM_2", "DEP_2", "PIL_2", "VEH_4WD", "DRN_1")],
          PIL, [CAR, FWD], [DR1],
          [job("X", "SITE_X", minutes=60, due=BEFORE),
           job("Y", "SITE_Y", minutes=90, required_vehicle_type="4wd"),
           job("Z", "SITE_Z", minutes=90, required_vehicle_type="4wd")],
          full(["DEP_1", "DEP_2", "SITE_X", "SITE_Y", "SITE_Z"], 25, 18))
    # C4 - access window + booking date + asymmetric travel over two days.
    write("c4_windows_asymmetric", "access window, booking date, asymmetric travel", (DAY1, DAY2),
          [bundle("TEAM_1", "DEP_1", "PIL_1", "VEH_CAR", "DRN_1")], PIL[:1], [CAR], [DR1],
          [job("P", "SITE_P", minutes=120, due=BEFORE, win=(DAY1, DAY1)),
           job("Q", "SITE_Q", minutes=60, access_start="08:00", access_end="09:45", win=(DAY1, DAY1)),
           job("R", "SITE_R", minutes=60, hard_earliest_date=DAY2, hard_latest_date=DAY2, win=(DAY1, DAY1))],
          [("DEP_1", "SITE_Q", 15, 12), ("SITE_Q", "SITE_P", 20, 15), ("SITE_P", "DEP_1", 40, 30),
           ("DEP_1", "SITE_P", 40, 30), ("SITE_P", "SITE_Q", 25, 18), ("SITE_Q", "DEP_1", 15, 12),
           ("DEP_1", "SITE_R", 10, 8), ("SITE_R", "DEP_1", 10, 8)])
    # C5 - route continuation: no direct DEP->X and no direct A->DEP, but DEP->A->X->DEP exists.
    write("c5_route_continuation", "valid multi-stop route without direct depot edges", (DAY1, DAY1),
          [bundle("TEAM_1", "DEP_1", "PIL_1", "VEH_CAR", "DRN_1")], PIL[:1], [CAR], [DR1],
          [job("A", "SITE_A", minutes=60), job("X", "SITE_X", minutes=60)],
          [("DEP_1", "SITE_A", 20, 15), ("SITE_A", "SITE_X", 20, 15), ("SITE_X", "DEP_1", 20, 15)])
    # C6 - work that version 1 cannot schedule, plus one ordinary job.
    write("c6_unschedulable_v1", "multi-day, too far for a day trip, incompatible, unconnected", (DAY1, DAY1),
          [bundle("TEAM_1", "DEP_1", "PIL_1", "VEH_CAR", "DRN_1")], PIL[:1], [CAR], [DR1],
          [job("OK", "SITE_OK", minutes=60),
           job("BIG", "SITE_BIG", area=600),  # 600 ha at 30 ha/h = 20 h: multi-day
           job("FAR", "SITE_FAR", minutes=60),  # 4 h each way: no same-day return
           job("THERMAL", "SITE_OK", minutes=30, equipment="thermal_camera", skills="thermal"),
           job("ISLAND", "SITE_ISLAND", minutes=30)],  # no travel edges at all
          [("DEP_1", "SITE_OK", 20, 15), ("SITE_OK", "DEP_1", 20, 15), ("DEP_1", "SITE_BIG", 20, 15),
           ("SITE_BIG", "DEP_1", 20, 15), ("DEP_1", "SITE_FAR", 240, 200), ("SITE_FAR", "DEP_1", 240, 200),
           ("SITE_OK", "SITE_FAR", 230, 190), ("SITE_FAR", "SITE_OK", 230, 190)])


if __name__ == "__main__":
    main()
