"""
IMSERV Platform — Field Operations & Engineer Planning Engine
Engineer scheduling, patch-level capacity planning, utilisation optimisation,
AI-driven understaffing prediction and workforce balancing.
Mirrors DAA's three-tier planning + OR-Tools philosophy.
"""
import math
import random
import statistics
from collections import defaultdict
from datetime import date, timedelta

from engine.ingestion import (
    get_engineers, iter_engineer_availability, get_capacity_demand,
    to_int, to_float, safe_pct
)

# ─────────────────────────────────────────────────────────────────────────────

UTILISATION_THRESHOLDS = {"Green": 75, "Amber": 90}  # % — above 90 = Red

# Seasonal absence shape factors by ISO week (Mon–Fri basis, UK field ops pattern).
# Normalised so August peak = 1.0; slider value (absence_rate_pct) sets the peak rate.
# e.g. at 4% peak: Aug absent = base_fte * 0.04 * 1.00, Mar/Oct = base_fte * 0.04 * 0.48.
PLANNING_BASE_FTE_2026 = 203

_SEASONAL_ABSENCE_FACTORS = {
    **{w: 0.82 for w in range(1,  5)},   # Jan  – post-Christmas / New Year
    **{w: 0.64 for w in range(5,  9)},   # Feb  – steady
    **{w: 0.48 for w in range(9, 14)},   # Mar  – low, pre-Easter
    **{w: 0.73 for w in range(14, 18)},  # Apr  – Easter / bank holidays
    **{w: 0.55 for w in range(18, 22)},  # May  – moderate
    **{w: 0.67 for w in range(22, 27)},  # Jun  – early summer leave
    **{w: 0.94 for w in range(27, 31)},  # Jul  – peak school summer holidays
    **{w: 1.00 for w in range(31, 36)},  # Aug  – peak summer (= defined max)
    **{w: 0.52 for w in range(36, 40)},  # Sep  – post-summer return
    **{w: 0.48 for w in range(40, 44)},  # Oct  – low season
    **{w: 0.55 for w in range(44, 48)},  # Nov  – steady
    **{w: 0.88 for w in range(48, 54)},  # Dec  – Christmas / year-end
}


def _seasonal_absence_factor(week: int) -> float:
    return _SEASONAL_ABSENCE_FACTORS.get(week, 1.0)


_WEEKDAY_NAMES = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

# 2026 dates from gov.uk bank-holidays.json. Scotland has a different summer
# holiday, St Andrew's Day, and the 2026 World Cup bank holiday.
_BANK_HOLIDAYS_2026 = {
    "england-and-wales": {
        date(2026, 1, 1),
        date(2026, 4, 3),
        date(2026, 4, 6),
        date(2026, 5, 4),
        date(2026, 5, 25),
        date(2026, 8, 31),
        date(2026, 12, 25),
        date(2026, 12, 28),
    },
    "scotland": {
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 4, 3),
        date(2026, 5, 4),
        date(2026, 5, 25),
        date(2026, 6, 15),
        date(2026, 8, 3),
        date(2026, 11, 30),
        date(2026, 12, 25),
        date(2026, 12, 28),
    },
}


def _bank_holiday_division(region_code: str) -> str:
    return "scotland" if region_code == "SCO" else "england-and-wales"


def _bank_holidays_for_region(region_code: str, year: int = 2026) -> set:
    if year != 2026:
        return set()
    return _BANK_HOLIDAYS_2026[_bank_holiday_division(region_code)]


def _parse_iso_date(value: str):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _weekday_index(row: dict) -> int:
    parsed = _parse_iso_date(row.get("avail_date"))
    if parsed:
        return parsed.weekday()
    return _WEEKDAY_NAMES.get(row.get("day_of_week"), -1)


def _weekdays_from_week_start(week_start: str, year: int, week: int) -> list:
    start = _parse_iso_date(week_start)
    if start is None:
        try:
            start = date.fromisocalendar(year, week, 1)
        except ValueError:
            start = date(year, 12, 29)
    return [start + timedelta(days=offset) for offset in range(5)]

# ─── Public API ───────────────────────────────────────────────────────────────

def get_field_ops_kpis(region_code: str = None, year: int = 2025) -> dict:
    """
    Field operations top-level KPIs: engineers, utilisation, productivity.

    Returns:
        dict with KPI values and RAG indicators
    """
    engs = get_engineers()
    if region_code:
        engs  = [e for e in engs  if e["region_code"] == region_code]

    total_engineers = len(engs)
    total_jobs = target_jobs = total_available_days = 0
    leave_days = sick_days = training_days = total_availability_days = 0
    util_values = []
    year_str = str(year)

    for a in iter_engineer_availability():
        if region_code and a.get("region_code") != region_code:
            continue
        if a.get("year") != year_str:
            continue

        total_availability_days += 1
        status = a.get("status")
        if status == "Available":
            total_available_days += 1
            total_jobs += to_int(a.get("jobs_completed"))
            target_jobs += to_int(a.get("jobs_target"))
            util = to_float(a.get("utilisation_pct"))
            if util > 0:
                util_values.append(util)
        elif status == "Annual Leave":
            leave_days += 1
        elif status == "Sick":
            sick_days += 1
        elif status == "Training":
            training_days += 1

    capacity_rows = [
        r for r in get_capacity_demand()
        if to_int(r.get("year")) == year and (not region_code or r.get("region_code") == region_code)
    ]
    total_capacity_jobs = sum(to_float(r.get("capacity_jobs")) for r in capacity_rows)
    total_demand_jobs = sum(to_float(r.get("demand_jobs")) for r in capacity_rows)
    avg_utilisation = safe_pct(total_demand_jobs, total_capacity_jobs)
    if not capacity_rows and util_values:
        avg_utilisation = round(statistics.mean(util_values), 1)

    productivity = round(total_jobs / max(total_available_days, 1), 2)
    completion_rate = safe_pct(total_jobs, target_jobs)

    rag = (
        "Red"   if avg_utilisation > 90 else
        "Amber" if avg_utilisation > 75 else
        "Green"
    )

    return {
        "total_engineers":   total_engineers,
        "avg_utilisation":   avg_utilisation,
        "utilisation_rag":   rag,
        "total_jobs_completed": total_jobs,
        "jobs_target":       target_jobs,
        "completion_rate":   completion_rate,
        "productivity_jobs_per_day": productivity,
        "available_days":    total_available_days,
        "leave_days":        leave_days,
        "sick_days":         sick_days,
        "training_days":     training_days,
        "absence_rate":      safe_pct(leave_days + sick_days, total_availability_days),
    }


def get_region_capacity_matrix(year: int = 2025) -> list:
    """
    Region × week capacity vs demand matrix with RAG status.

    Returns:
        list of weekly capacity records with utilisation and RAG
    """
    rows = get_capacity_demand()
    rows = [r for r in rows if to_int(r.get("year")) == year]

    # Aggregate to region level
    by_region_week: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        key = (r["region_code"], r["week_number"])
        by_region_week[key]["capacity_jobs"]      += to_float(r["capacity_jobs"])
        by_region_week[key]["demand_jobs"]         += to_float(r["demand_jobs"])
        by_region_week[key]["available_engineers"] += to_float(r["available_engineers"])

    result = []
    for (region_code, week), d in sorted(by_region_week.items()):
        util = safe_pct(d["demand_jobs"], d["capacity_jobs"])
        rag  = "Red" if util > 90 else ("Amber" if util > 75 else "Green")
        result.append({
            "region_code":         region_code,
            "week_number":         to_int(week),
            "available_engineers": int(d["available_engineers"]),
            "capacity_jobs":       int(d["capacity_jobs"]),
            "demand_jobs":         int(d["demand_jobs"]),
            "gap_jobs":            int(d["capacity_jobs"] - d["demand_jobs"]),
            "utilisation_pct":     util,
            "rag":                 rag,
        })
    return result


def get_patch_level_plan(region_code: str, week_number: int = None, year: int = 2025) -> list:
    """
    Patch-level capacity planning for a given region.

    Parameters:
        region_code: Region to drill into
        week_number: Specific week (None = all weeks for year)
        year: Calendar year

    Returns:
        list of patch-level records with capacity, demand, and engineer allocation
    """
    rows = get_capacity_demand()
    rows = [r for r in rows if r["region_code"] == region_code and to_int(r.get("year")) == year]
    if week_number is not None:
        rows = [r for r in rows if to_int(r.get("week_number")) == week_number]

    result = []
    for r in rows:
        util = to_float(r["utilisation_pct"])
        rag  = r.get("rag_status", "Green")
        gap  = to_int(r["gap_jobs"])

        ai_flag = None
        if util > 90:
            ai_flag = {"type": "understaffing", "message": f"Patch {r['patch_code']} exceeds 90% utilisation — risk of missed jobs"}
        elif util < 40 and gap > 10:
            ai_flag = {"type": "overstaffing", "message": f"Patch {r['patch_code']} underutilised — consider rebalancing to high-demand patches"}

        result.append({
            "patch_code":          r["patch_code"],
            "week_number":         to_int(r["week_number"]),
            "available_engineers": to_int(r["available_engineers"]),
            "capacity_jobs":       to_int(r["capacity_jobs"]),
            "demand_jobs":         to_int(r["demand_jobs"]),
            "gap_jobs":            gap,
            "utilisation_pct":     util,
            "rag":                 rag,
            "ai_flag":             ai_flag,
        })

    result.sort(key=lambda x: -x["utilisation_pct"])
    return result


def get_engineer_performance(region_code: str = None, year: int = 2025, top_n: int = 20) -> list:
    """
    Engineer-level productivity and performance metrics.

    Returns:
        list of engineer performance records
    """
    by_engineer: dict = defaultdict(lambda: defaultdict(float))
    year_str = str(year)
    for a in iter_engineer_availability():
        if region_code and a.get("region_code") != region_code:
            continue
        if a.get("year") != year_str or a.get("status") != "Available":
            continue

        eng = a["engineer_id"]
        by_engineer[eng]["days"]           += 1
        by_engineer[eng]["jobs_completed"] += to_float(a["jobs_completed"])
        by_engineer[eng]["jobs_target"]    += to_float(a["jobs_target"])
        by_engineer[eng]["region_code"]     = a["region_code"]
        by_engineer[eng]["patch_code"]      = a["patch_code"]
        by_engineer[eng]["employment_type"] = a["employment_type"]

    result = []
    for eng_id, d in by_engineer.items():
        days = d["days"]
        jobs = d["jobs_completed"]
        tgt  = d["jobs_target"]
        avg_daily_jobs = round(jobs / max(days, 1), 2)
        achievement    = safe_pct(jobs, tgt)
        result.append({
            "engineer_id":       eng_id,
            "region_code":       d["region_code"],
            "patch_code":        d["patch_code"],
            "employment_type":   d["employment_type"],
            "working_days":      int(days),
            "jobs_completed":    int(jobs),
            "jobs_target":       int(tgt),
            "avg_daily_jobs":    avg_daily_jobs,
            "achievement_pct":   achievement,
        })

    result.sort(key=lambda x: -x["achievement_pct"])
    return result[:top_n]


def predict_understaffing(region_code: str, look_ahead_weeks: int = 8) -> list:
    """
    AI-driven understaffing prediction for next N weeks.

    Returns:
        list of weekly risk assessments with recommended actions
    """
    capacity = get_capacity_demand()
    if region_code:
        capacity = [r for r in capacity if r["region_code"] == region_code]

    # Use 2025 actuals as pattern; project into 2026
    historical = sorted(
        [r for r in capacity if to_int(r.get("year")) == 2025],
        key=lambda x: x.get("week_number", "0")
    )

    if not historical:
        return []

    # Get seasonal demand pattern from last 12 weeks
    last_12 = historical[-12:]
    avg_util = statistics.mean([to_float(r["utilisation_pct"]) for r in last_12])
    avg_cap  = statistics.mean([to_float(r["capacity_jobs"])   for r in last_12])
    avg_dem  = statistics.mean([to_float(r["demand_jobs"])     for r in last_12])

    forecasts = []
    for i in range(1, look_ahead_weeks + 1):
        week_n = (to_int(historical[-1].get("week_number", 52)) + i - 1) % 52 + 1
        # Seasonal factor
        sf = 1.0 + 0.18 * math.sin(2 * math.pi * (week_n - 28) / 52)
        dem_forecast = avg_dem * sf * (1.0 + random.gauss(0, 0.04))
        cap_forecast = avg_cap * random.uniform(0.88, 0.96)  # account for absence

        util = safe_pct(dem_forecast, cap_forecast)
        gap  = int(cap_forecast - dem_forecast)
        risk = "Critical" if util > 95 else ("High" if util > 85 else ("Medium" if util > 75 else "Low"))

        recommendation = ""
        if util > 95:
            engineers_needed = math.ceil((dem_forecast - cap_forecast) / 4)
            recommendation = f"Deploy {engineers_needed} additional engineers to {region_code} — demand exceeds capacity by {abs(gap)} jobs/week"
        elif util > 85:
            recommendation = f"Monitor closely — consider pulling resource from lower-demand patches in week {week_n}"
        elif util < 55:
            recommendation = f"Overstaffed — redeploy engineers to higher demand regions in week {week_n}"

        forecasts.append({
            "week_number":      week_n,
            "capacity_jobs":    int(cap_forecast),
            "demand_forecast":  int(dem_forecast),
            "gap":              gap,
            "utilisation_pct":  util,
            "risk_level":       risk,
            "recommendation":   recommendation,
        })

    return forecasts


def _aggregate_capacity(year: int, region_code: str = None, key_fields: tuple = ("region_code", "week_number")) -> list:
    rows = [
        r for r in get_capacity_demand()
        if to_int(r.get("year")) == year and (not region_code or r.get("region_code") == region_code)
    ]
    grouped = defaultdict(lambda: {"capacity_jobs": 0.0, "demand_jobs": 0.0, "available_engineers": 0.0})
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        grouped[key]["capacity_jobs"] += to_float(row.get("capacity_jobs"))
        grouped[key]["demand_jobs"] += to_float(row.get("demand_jobs"))
        grouped[key]["available_engineers"] += to_float(row.get("available_engineers"))
        if row.get("week_start") and not grouped[key].get("week_start"):
            grouped[key]["week_start"] = row.get("week_start")

    result = []
    for key, values in grouped.items():
        item = dict(zip(key_fields, key))
        item.update(values)
        result.append(item)
    return result


def get_capacity_forecast_2026(
    region_code: str = None,
    target_utilisation_pct: float = 78,
    jobs_per_fte_day: float = 4,
    absence_rate_pct: float = None,
) -> dict:
    """
    Demand-led 2026 resource forecast.
    Daily required FTE = daily demand / jobs per FTE per day.
    Net forecast FTE = required FTE - absent FTE, then converted back to
    forecast job capacity for the weekly planning graph.
    """
    jobs_per_day = _clamp_number(jobs_per_fte_day, 4, 0.5, 8, float)
    absence_override = None
    if absence_rate_pct is not None:
        absence_override = _clamp_number(absence_rate_pct, 4, 0, 10, float) / 100.0
    capacity_2025 = _aggregate_capacity(2025, region_code, ("region_code", "week_number"))
    capacity_2026 = _aggregate_capacity(2026, region_code, ("region_code", "week_number"))

    availability_day_keys = set()
    fte_by_day = defaultdict(float)
    absent_by_day = defaultdict(float)
    absent_by_weekday = defaultdict(float)
    fallback_absence_by_weekday = defaultdict(list)
    base_fte_by_year_region = defaultdict(set)
    _WEEKENDS = {"Saturday", "Sunday"}
    for row in iter_engineer_availability():
        if row.get("day_of_week") in _WEEKENDS:
            continue
        row_region = row.get("region_code")
        if region_code and row_region != region_code:
            continue
        year = to_int(row.get("year"))
        if year not in (2025, 2026):
            continue
        week = to_int(row.get("week"))
        weekday = _weekday_index(row)
        if weekday < 0 or weekday >= 5:
            continue
        day_key = (year, week, row_region, row.get("avail_date"))
        availability_day_keys.add(day_key)
        fte_by_day[day_key] += 1
        if row.get("status") != "Available":
            absent_by_day[day_key] += 1
            absent_by_weekday[(year, week, row_region, weekday)] += 1
        base_fte_by_year_region[(year, row_region)].add(row.get("engineer_id"))

    regions_with_2026 = {
        region
        for (year, region), engineers in base_fte_by_year_region.items()
        if year == 2026 and engineers
    }
    regions_with_2025 = {
        region
        for (year, region), engineers in base_fte_by_year_region.items()
        if year == 2025 and engineers
    }
    base_fte_by_region = {}
    for region in regions_with_2026 | regions_with_2025:
        source_year = 2026 if region in regions_with_2026 else 2025
        base_fte_by_region[region] = len(base_fte_by_year_region[(source_year, region)])
    total_base_fte = sum(base_fte_by_region.values()) or 1
    planning_scale = PLANNING_BASE_FTE_2026 / total_base_fte
    planning_base_fte_by_region = {
        region: base_fte * planning_scale
        for region, base_fte in base_fte_by_region.items()
    }

    for (year, week, region, weekday), absent in absent_by_weekday.items():
        if year == 2025:
            scale = planning_base_fte_by_region.get(region, 0) / max(base_fte_by_region.get(region, 0), 1)
            fallback_absence_by_weekday[(region, weekday)].append(absent * scale)

    avg_absence_by_weekday = {
        key: statistics.mean(values)
        for key, values in fallback_absence_by_weekday.items()
        if values
    }

    weekly_2025 = defaultdict(float)
    for point in capacity_2025:
        weekly_2025[to_int(point.get("week_number"))] += point["capacity_jobs"]

    weekly_map = defaultdict(lambda: {
        "demand_jobs": 0.0,
        "current_capacity_jobs": 0.0,
        "forecast_capacity_jobs": 0.0,
        "required_fte_days": 0.0,
        "net_forecast_fte_days": 0.0,
        "absent_fte_days": 0.0,
        "bank_holiday_days": 0,
        "bank_holiday_fte_days": 0.0,
        "working_days": 0,
    })
    regional_map = defaultdict(lambda: {
        "demand_jobs": 0.0,
        "current_capacity_jobs": 0.0,
        "forecast_capacity_jobs": 0.0,
        "required_fte_days": 0.0,
        "net_forecast_fte_days": 0.0,
        "absent_fte_days": 0.0,
        "bank_holiday_days": 0,
        "bank_holiday_fte_days": 0.0,
        "working_days": 0,
    })

    for point in capacity_2026:
        region = point.get("region_code")
        week = to_int(point.get("week_number"))
        demand = point["demand_jobs"]
        current_capacity = point["capacity_jobs"]
        week_dates = _weekdays_from_week_start(point.get("week_start"), 2026, week)
        bank_holidays = _bank_holidays_for_region(region, 2026)
        operational_day_count = sum(1 for day in week_dates if day not in bank_holidays) or len(week_dates)
        working_day_count = len(week_dates) or 5
        daily_demand = demand / max(operational_day_count, 1)

        forecast_capacity = 0.0
        required_fte_days = 0.0
        net_fte_days = 0.0
        absent_fte_days = 0.0
        bank_holiday_days = 0
        bank_holiday_fte_days = 0.0
        region_base_fte = planning_base_fte_by_region.get(region, 0)
        region_scale = region_base_fte / max(base_fte_by_region.get(region, 0), 1)
        seasonal_factor = _seasonal_absence_factor(week)
        for day in week_dates:
            day_key = (2026, week, region, str(day))
            base_fte = region_base_fte
            required_fte = daily_demand / jobs_per_day
            if day in bank_holidays:
                absent = base_fte
                bank_holiday_days += 1
                bank_holiday_fte_days += base_fte
                required_fte = 0.0
            else:
                if day_key in availability_day_keys:
                    exact_absent = absent_by_day.get(day_key, 0.0) * region_scale
                else:
                    exact_absent = absent_by_weekday.get((2025, week, region, day.weekday()))
                    if exact_absent is not None:
                        exact_absent *= region_scale
                if exact_absent is None:
                    exact_absent = avg_absence_by_weekday.get((region, day.weekday()), 0.0)
                scenario_absent = 0.0
                if absence_override is not None:
                    scenario_absent = base_fte * absence_override * seasonal_factor
                absent = max(exact_absent, scenario_absent)
            net_fte = max(base_fte - absent, 0)
            required_fte_days += required_fte
            net_fte_days += net_fte
            absent_fte_days += absent
            forecast_capacity += net_fte * jobs_per_day

        week_bucket = weekly_map[week]
        week_bucket["demand_jobs"] += demand
        week_bucket["current_capacity_jobs"] += current_capacity
        week_bucket["forecast_capacity_jobs"] += forecast_capacity
        week_bucket["required_fte_days"] += required_fte_days
        week_bucket["net_forecast_fte_days"] += net_fte_days
        week_bucket["absent_fte_days"] += absent_fte_days
        week_bucket["bank_holiday_days"] += bank_holiday_days
        week_bucket["bank_holiday_fte_days"] += bank_holiday_fte_days
        week_bucket["working_days"] = max(week_bucket["working_days"], working_day_count)

        region_bucket = regional_map[region]
        region_bucket["demand_jobs"] += demand
        region_bucket["current_capacity_jobs"] += current_capacity
        region_bucket["forecast_capacity_jobs"] += forecast_capacity
        region_bucket["required_fte_days"] += required_fte_days
        region_bucket["net_forecast_fte_days"] += net_fte_days
        region_bucket["absent_fte_days"] += absent_fte_days
        region_bucket["bank_holiday_days"] += bank_holiday_days
        region_bucket["bank_holiday_fte_days"] += bank_holiday_fte_days
        region_bucket["working_days"] += working_day_count

    weekly = []
    for week, values in sorted(weekly_map.items()):
        current_capacity = values["current_capacity_jobs"]
        forecast_capacity = values["forecast_capacity_jobs"]
        demand = values["demand_jobs"]
        working_days = max(values["working_days"], 1)
        capacity_2025_jobs = weekly_2025.get(week, 0)
        weekly.append({
            "week_number": week,
            "demand_jobs": int(round(demand)),
            "capacity_2025_jobs": int(round(capacity_2025_jobs)),
            "capacity_2025_fte": round(capacity_2025_jobs / max(jobs_per_day * 7, 1), 1),
            "current_capacity_jobs": int(round(current_capacity)),
            "current_capacity_fte": round(current_capacity / max(jobs_per_day * working_days, 1), 1),
            "forecast_capacity_jobs": int(round(forecast_capacity)),
            "gap_jobs": int(round(forecast_capacity - demand)),
            "planned_gap_jobs": int(round(current_capacity - demand)),
            "required_fte": round(values["required_fte_days"] / working_days, 1),
            "net_forecast_fte": round(values["net_forecast_fte_days"] / working_days, 1),
            "absent_fte": round(values["absent_fte_days"] / working_days, 1),
            "bank_holiday_days": values["bank_holiday_days"],
            "bank_holiday_fte": round(values["bank_holiday_fte_days"] / working_days, 1),
            "fte_gap": round((values["net_forecast_fte_days"] - values["required_fte_days"]) / working_days, 1),
            "utilisation_pct": safe_pct(demand, forecast_capacity),
            "planned_utilisation_pct": safe_pct(demand, current_capacity),
        })

    regions = []
    for region, values in sorted(regional_map.items()):
        demand = values["demand_jobs"]
        current_capacity = values["current_capacity_jobs"]
        forecast_capacity = values["forecast_capacity_jobs"]
        working_days = max(values["working_days"], 1)
        required_fte = values["required_fte_days"] / working_days
        net_fte = values["net_forecast_fte_days"] / working_days
        absent_fte = values["absent_fte_days"] / working_days
        gap = forecast_capacity - demand
        util = safe_pct(demand, forecast_capacity)
        regions.append({
            "region_code": region,
            "demand_jobs": int(round(demand)),
            "current_capacity_jobs": int(round(current_capacity)),
            "current_capacity_fte": round(current_capacity / max(jobs_per_day * working_days, 1), 1),
            "forecast_capacity_jobs": int(round(forecast_capacity)),
            "gap_jobs": int(round(gap)),
            "planned_gap_jobs": int(round(current_capacity - demand)),
            "utilisation_pct": util,
            "planned_utilisation_pct": safe_pct(demand, current_capacity),
            "required_fte": round(required_fte, 1),
            "net_forecast_fte": round(net_fte, 1),
            "absent_fte": round(absent_fte, 1),
            "bank_holiday_days": values["bank_holiday_days"],
            "bank_holiday_fte": round(values["bank_holiday_fte_days"] / working_days, 1),
            "fte_gap": round(net_fte - required_fte, 1),
            "risk": "Red" if gap < 0 else ("Amber" if util > 85 else "Green"),
        })

    total_demand = sum(item["demand_jobs"] for item in weekly)
    total_current_capacity = sum(item["current_capacity_jobs"] for item in weekly)
    total_forecast_capacity = sum(item["forecast_capacity_jobs"] for item in weekly)
    total_2025_capacity = sum(item["capacity_2025_jobs"] for item in weekly)

    return {
        "year": 2026,
        "method": {
            "name": "Demand-led FTE forecast",
            "jobs_per_fte_day": jobs_per_day,
            "planning_base_fte": PLANNING_BASE_FTE_2026,
            "formula": "daily capacity FTE = 203 planning roster FTE - real leave/absence - UK bank holidays; weekly demand is converted using jobs per FTE per working day",
        },
        "kpis": {
            "total_demand_jobs": total_demand,
            "capacity_2025_jobs": total_2025_capacity,
            "current_capacity_jobs": total_current_capacity,
            "forecast_capacity_jobs": total_forecast_capacity,
            "gap_jobs": total_forecast_capacity - total_demand,
            "planned_gap_jobs": total_current_capacity - total_demand,
            "avg_utilisation": safe_pct(total_demand, total_forecast_capacity),
            "planned_utilisation": safe_pct(total_demand, total_current_capacity),
            "avg_required_fte": round(sum(item["required_fte"] for item in weekly) / max(len(weekly), 1), 1),
            "avg_net_forecast_fte": round(sum(item["net_forecast_fte"] for item in weekly) / max(len(weekly), 1), 1),
            "avg_absent_fte": round(sum(item["absent_fte"] for item in weekly) / max(len(weekly), 1), 1),
            "avg_bank_holiday_fte": round(sum(item["bank_holiday_fte"] for item in weekly) / max(len(weekly), 1), 1),
            "avg_2025_capacity_fte": round(sum(item["capacity_2025_fte"] for item in weekly) / max(len(weekly), 1), 1),
            "avg_current_capacity_fte": round(sum(item["current_capacity_fte"] for item in weekly) / max(len(weekly), 1), 1),
            "avg_fte_gap": round(sum(item["fte_gap"] for item in weekly) / max(len(weekly), 1), 1),
            "planning_base_fte": PLANNING_BASE_FTE_2026,
            "red_regions": sum(1 for region in regions if region["risk"] == "Red"),
        },
        "weekly": weekly,
        "regions": regions,
    }


def _clamp_number(value, default, min_value, max_value, cast=float):
    try:
        value = cast(value)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def optimise_workforce_allocation(
    year: int = 2026,
    target_utilisation_pct: float = 72,
    jobs_per_fte_day: float = 4,
    absence_rate_pct: float = 15,
    **kwargs,  # Accept legacy params silently
) -> dict:
    """
    Workforce rebalancing recommendations based strictly on Demand vs Capacity FTE.
    Capacity Forecast FTE = (Engineers - (Engineers * absence rate)) * utilization
    Required FTE = demand_jobs / (jobs_per_fte_day * 5 * 52)
    """
    target_util = _clamp_number(target_utilisation_pct, 72, 10, 200, float) / 100.0
    jobs_day    = _clamp_number(jobs_per_fte_day, 4, 0.5, 8, float)
    absence     = _clamp_number(absence_rate_pct, 15, 0, 60, float) / 100.0

    # ── Pull demand-forecast data ─────────────────────────────────────────────
    forecast = get_capacity_forecast_2026(
        region_code=None,
        target_utilisation_pct=target_utilisation_pct,
        jobs_per_fte_day=jobs_day,
        absence_rate_pct=absence_rate_pct,
    )
    forecast_regions = {r["region_code"]: r for r in forecast.get("regions", [])}

    region_codes = ["NW", "NE", "MID", "SE", "SW", "WAL", "SCO", "YRK"]
    engineer_counts = {}
    for rc in region_codes:
        kpis = get_field_ops_kpis(rc, year)
        engineer_counts[rc] = kpis["total_engineers"]

    # ── Build region state ───────────────────────────────────────────────────
    region_state = {}
    for rc in region_codes:
        fr = forecast_regions.get(rc, {})
        engineers    = engineer_counts.get(rc, 0)
        required_fte = fr.get("required_fte", 0.0)
        # Optimisation baseline requested by planning:
        # capacity forecast FTE = (FTE forecast from demand - absence) * utilisation.
        capacity_fte = (required_fte - (required_fte * absence)) * target_util
        fte_gap = capacity_fte - required_fte

        region_state[rc] = {
            "region_code":          rc,
            "engineers_before":     engineers,
            "engineers_after":      engineers,
            "required_fte":         required_fte,
            "forecast_capacity_fte": capacity_fte,
            "capacity_fte_before":  capacity_fte,
            "capacity_fte_after":   capacity_fte,
            "demand_jobs":          fr.get("demand_jobs", 0),
            "fte_gap_before":       fte_gap,
            "fte_gap_after":        fte_gap,
        }

    # ── Classify sources (surplus) and destinations (deficit) ────────────────
    sources      = []
    destinations = []
    
    # 1 engineer provides this much productive FTE
    fte_per_engineer = (1.0 - absence) * target_util

    for rc, state in region_state.items():
        gap = state["fte_gap_before"]
        if gap > 0 and state["engineers_before"] > 0:
            surplus_engineers = int(gap / max(fte_per_engineer, 0.01))
            if surplus_engineers > 0:
                sources.append({"region_code": rc, "available": surplus_engineers, "gap": gap})
        elif gap < 0:
            needed_engineers = math.ceil(abs(gap) / max(fte_per_engineer, 0.01))
            if needed_engineers > 0:
                destinations.append({"region_code": rc, "needed": needed_engineers, "gap": gap})

    # Most surplus first, most deficit first
    sources.sort(key=lambda x: x["gap"], reverse=True)
    destinations.sort(key=lambda x: x["gap"])

    # ── Greedy rebalancing loop ───────────────────────────────────────────────
    recommendations = []
    
    for dest in destinations:
        for src in sources:
            if dest["needed"] <= 0:
                break
            if src["available"] <= 0:
                continue

            engineers_to_move = min(src["available"], dest["needed"])
            if engineers_to_move <= 0:
                continue

            src_state  = region_state[src["region_code"]]
            dest_state = region_state[dest["region_code"]]

            # Update source
            src_state["engineers_after"]     -= engineers_to_move
            src_state["capacity_fte_after"]  -= engineers_to_move * fte_per_engineer
            src_state["fte_gap_after"]        = src_state["capacity_fte_after"] - src_state["required_fte"]

            # Update destination
            dest_state["engineers_after"]    += engineers_to_move
            dest_state["capacity_fte_after"] += engineers_to_move * fte_per_engineer
            dest_state["fte_gap_after"]       = dest_state["capacity_fte_after"] - dest_state["required_fte"]

            src["available"] -= engineers_to_move
            dest["needed"]   -= engineers_to_move

            recommendations.append({
                "from_region":     src["region_code"],
                "to_region":       dest["region_code"],
                "action":          "move",
                "engineers":       engineers_to_move,
                "from_gap_before": round(src_state["fte_gap_before"], 1),
                "from_gap_after":  round(src_state["fte_gap_after"], 1),
                "to_gap_before":   round(dest_state["fte_gap_before"], 1),
                "to_gap_after":    round(dest_state["fte_gap_after"], 1),
                "rationale": (
                    f"{src['region_code']} has a surplus of {src_state['fte_gap_before']:.1f} FTE. "
                    f"{dest['region_code']} has a deficit of {dest_state['fte_gap_before']:.1f} FTE."
                ),
            })

        if dest["needed"] > 0:
            dest_state = region_state[dest["region_code"]]
            engineers_to_add = dest["needed"]
            dest_before = dest_state["fte_gap_after"]

            dest_state["engineers_after"] += engineers_to_add
            dest_state["capacity_fte_after"] += engineers_to_add * fte_per_engineer
            dest_state["fte_gap_after"] = dest_state["capacity_fte_after"] - dest_state["required_fte"]
            dest["needed"] = 0

            recommendations.append({
                "from_region": "Flex Pool",
                "to_region": dest["region_code"],
                "action": "add",
                "engineers": engineers_to_add,
                "from_gap_before": 0,
                "from_gap_after": 0,
                "to_gap_before": round(dest_before, 1),
                "to_gap_after": round(dest_state["fte_gap_after"], 1),
                "rationale": (
                    f"{dest['region_code']} has no available surplus donor region. "
                    f"Add {engineers_to_add} flexible engineers to close the forecast FTE deficit."
                ),
            })

    total_moved = sum(r["engineers"] for r in recommendations)
    total_gap_before = sum(s["fte_gap_before"] for s in region_state.values())
    total_gap_after  = sum(s["fte_gap_after"] for s in region_state.values())

    overstaffed = [rc for rc, s in region_state.items() if s["fte_gap_after"] > 0]
    understaffed = [rc for rc, s in region_state.items() if s["fte_gap_after"] < 0]

    return {
        "parameters": {
            "target_utilisation_pct":    target_utilisation_pct,
            "jobs_per_fte_day":          jobs_day,
            "absence_rate_pct":          round(absence * 100, 1),
        },
        "overstaffed_regions":  overstaffed,
        "understaffed_regions": understaffed,
        "recommendations":      recommendations,
        "regional_before_after": [
            {
                "region_code":          rc,
                "engineers_before":     s["engineers_before"],
                "engineers_after":      s["engineers_after"],
                "demand_jobs":          s["demand_jobs"],
                "required_fte":         round(s["required_fte"], 1),
                "forecast_capacity_fte": round(s["forecast_capacity_fte"], 1),
                "capacity_fte_before":  round(s["capacity_fte_before"], 1),
                "capacity_fte_after":   round(s["capacity_fte_after"], 1),
                "fte_gap_before":       round(s["fte_gap_before"], 1),
                "fte_gap_after":        round(s["fte_gap_after"], 1),
            }
            for rc, s in sorted(region_state.items())
        ],
        "total_engineers_moved": total_moved,
        "total_gap_before":      round(total_gap_before, 1),
        "total_gap_after":       round(total_gap_after, 1),
    }
