"""Estimated costs of a proposed itinerary from explicit scenario rates.

Each component is applied once at its stated level:
  trip                 - 1 per bundle-day route (depot -> stops -> depot)
  vehicle_day          - 1 per bundle-day route
  distance_km          - total km of all legs, including the return leg
  fuel_km              - total km, unless the applicable distance or vehicle-day
                         rate already includes fuel (then not added again)
  personnel_person_day - number of pilots in the bundle
  allowance_person_day - number of pilots in the bundle
Missing rates or distances stay unknown (amount None) and make coverage
incomplete; they are never replaced by zero. Accommodation is not applicable
to return-to-base routes. All values are ESTIMATES, not actual expenditure,
and no historical expense summary is added to them.
"""

from __future__ import annotations

from agriflight.scheduling.contracts import COST_CATEGORIES, CostRate, Scenario
from agriflight.scheduling.rule_baseline import RouteDay

ESTIMATED = "estimated"
UNIT = {"trip": "trip", "vehicle_day": "vehicle-day", "distance_km": "km", "fuel_km": "km",
        "personnel_person_day": "person-day", "allowance_person_day": "person-day"}


def find_rate(scenario: Scenario, category: str, vehicle_type: str | None) -> CostRate | None:
    exact = [r for r in scenario.cost_rates if r.category == category and r.applies_to == vehicle_type]
    if exact:
        return exact[0]
    generic = [r for r in scenario.cost_rates if r.category == category and r.applies_to == "*"]
    return generic[0] if generic else None


def route_km(route: RouteDay) -> float | None:
    kms = [leg[3] for leg in route.legs]
    return None if any(k is None for k in kms) else float(sum(kms))


def route_costs(scenario: Scenario, route: RouteDay) -> list[dict]:
    bundle = next(b for b in scenario.bundles if b.bundle_id == route.bundle_id)
    vtype = scenario.vehicle_types.get(bundle.vehicle_id)
    km = route_km(route)
    persons = len(bundle.pilot_ids)
    quantities = {"trip": 1.0, "vehicle_day": 1.0, "distance_km": km, "fuel_km": km,
                  "personnel_person_day": float(persons), "allowance_person_day": float(persons)}
    fuel_included_by = [r.rate_id for c in ("distance_km", "vehicle_day")
                        if (r := find_rate(scenario, c, vtype)) and r.includes_fuel
                        and c in scenario.cost_categories_included]
    rows = []
    for category in COST_CATEGORIES:
        rate = find_rate(scenario, category, vtype)
        qty = quantities[category]
        row = {"bundle_id": route.bundle_id, "day": route.day, "category": category, "unit": UNIT[category],
               "quantity": qty, "rate_id": rate.rate_id if rate else None,
               "rate_lkr": rate.amount_lkr if rate else None, "amount_lkr": None, "basis": ESTIMATED}
        if category not in scenario.cost_categories_included:
            row["status"] = "excluded_by_scenario"
        elif category == "fuel_km" and fuel_included_by:
            row["status"] = f"included_in_rate {','.join(fuel_included_by)}"
        elif rate is None:
            row["status"] = "rate_not_configured"
        elif rate.amount_lkr is None:
            row["status"] = "rate_unknown"
        elif qty is None:
            row["status"] = "distance_unknown"
        else:
            row["amount_lkr"] = round(qty * rate.amount_lkr, 2)
            row["status"] = ESTIMATED
        rows.append(row)
    rows.append({"bundle_id": route.bundle_id, "day": route.day, "category": "accommodation", "unit": "night",
                 "quantity": 0.0, "rate_id": None, "rate_lkr": None, "amount_lkr": None, "basis": ESTIMATED,
                 "status": "not_applicable_return_to_base"})
    return rows


def is_covered(status: str) -> bool:
    return status == ESTIMATED or status.startswith("included_in_rate") or status in (
        "excluded_by_scenario", "not_applicable_return_to_base")


def cost_summary(rows: list[dict]) -> dict[str, object]:
    known = [r["amount_lkr"] for r in rows if r["amount_lkr"] is not None]
    gaps = sorted({f"{r['category']} ({r['status']})" for r in rows if not is_covered(r["status"])})
    return {
        "estimated_known_total_lkr": round(sum(known), 2) if known else None,
        "coverage_complete": not gaps,
        "missing_components": gaps,
        "bundle_day_routes_costed": len({(r["bundle_id"], r["day"]) for r in rows}),
        "label": "Estimated planning cost from scenario rates - not actual expenditure or realised savings.",
    }
