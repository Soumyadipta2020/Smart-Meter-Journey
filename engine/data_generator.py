"""
IMSERV Platform - Connected Synthetic Dataset Generator.

The generated data now has a single source of truth:
data/inputs/master_operations.csv

The dashboard-facing CSVs are derived from that master ledger so the Journey,
Contact Centre, Cancellations, Field Ops, and Financial tabs reconcile through
the same job, engineer, patch, region, channel, and date keys.
"""
import csv
import json
import random
import math
from collections import defaultdict
from datetime import date, timedelta, datetime, UTC
from pathlib import Path

RANDOM_SEED = 42

BASE_DIR = Path(__file__).resolve().parent.parent
INPUTS_DIR = BASE_DIR / "data" / "inputs"
INPUTS_DIR.mkdir(parents=True, exist_ok=True)
SUPPLIERS_FILE = INPUTS_DIR / "suppliers.csv"

REGIONS = {
    "NW": {"name": "North West", "base_jobs": 1890, "engineers": 38, "patches": 6},
    "NE": {"name": "North East", "base_jobs": 1395, "engineers": 28, "patches": 5},
    "MID": {"name": "Midlands", "base_jobs": 2295, "engineers": 46, "patches": 7},
    "SE": {"name": "South East", "base_jobs": 2610, "engineers": 52, "patches": 8},
    "SW": {"name": "South West", "base_jobs": 1215, "engineers": 24, "patches": 4},
    "WAL": {"name": "Wales", "base_jobs": 990, "engineers": 20, "patches": 3},
    "SCO": {"name": "Scotland", "base_jobs": 1305, "engineers": 26, "patches": 4},
    "YRK": {"name": "Yorkshire", "base_jobs": 1710, "engineers": 34, "patches": 5},
}

METER_TYPES = ["SMETS1", "SMETS2", "SMETS2_GAS", "IHD"]
METER_WEIGHTS = [0.18, 0.45, 0.28, 0.09]

JOB_TYPES = ["NEW_INSTALL", "EXCHANGE", "REPAIR", "REMOVAL"]
JOB_TYPE_WEIGHTS = [0.35, 0.40, 0.18, 0.07]

CHANNELS = ["Phone", "Web", "App", "SMS", "IVR", "Agent Callback"]
CHANNEL_WEIGHTS = [0.38, 0.25, 0.18, 0.08, 0.07, 0.04]

CANCEL_REASONS = [
    "Customer not home",
    "No access to meter",
    "Wrong meter type",
    "Safety concern",
    "Customer refused",
    "Equipment fault",
    "Rescheduled by customer",
    "Work order error",
]
ABORT_REASONS = [
    "No access",
    "Safety hazard",
    "Faulty meter location",
    "Customer unavailable",
    "Health & safety concern",
    "Parts not available",
]

EMPLOYMENT_TYPES = ["Permanent", "Contract", "Agency"]
EMP_WEIGHTS = [0.70, 0.20, 0.10]

REVENUE_MAP = {"NEW_INSTALL": 185.0, "EXCHANGE": 165.0, "REPAIR": 120.0, "REMOVAL": 90.0}
COST_MAP = {"NEW_INSTALL": 95.0, "EXCHANGE": 82.0, "REPAIR": 65.0, "REMOVAL": 48.0}
ABORT_COST = 38.0
OVERHEAD_PCT = 0.22


def _load_suppliers() -> list[str]:
    if not SUPPLIERS_FILE.exists():
        return ["Unassigned Supplier"]
    with open(SUPPLIERS_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        suppliers = [r.get("supplier_name", "").strip() for r in reader]
    return [s for s in suppliers if s] or ["Unassigned Supplier"]


def _build_supplier_pool(suppliers: list[str]) -> list[str]:
    pool = []
    for idx, supplier in enumerate(suppliers):
        weight = max(1, round(60 / ((idx + 5) ** 0.55)))
        pool.extend([supplier] * weight)
    return pool or ["Unassigned Supplier"]


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def week_of_year(d: date) -> int:
    return d.isocalendar()[1]


def seasonal_factor(d: date, amplitude: float = 0.20, peak_week: int = 28) -> float:
    w = week_of_year(d)
    return 1.0 + amplitude * math.sin(2 * math.pi * (w - peak_week) / 52)


def day_of_week_factor(d: date) -> float:
    factors = {0: 1.05, 1: 1.10, 2: 1.08, 3: 1.06, 4: 0.95, 5: 0.45, 6: 0.25}
    return factors[d.weekday()]


def gauss_noise(scale: float = 0.06) -> float:
    return 1.0 + random.gauss(0, scale)


def write_csv(filename: str, rows: list, fieldnames: list):
    path = INPUTS_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  OK  {filename}  ({len(rows):,} rows)")


def _month_name(month: int) -> str:
    return date(2025, month, 1).strftime("%B")


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _build_engineers() -> tuple[list, dict, dict]:
    engineers_rows = []
    by_patch = defaultdict(list)
    by_id = {}
    emp_counter = 1

    for region_code, rinfo in REGIONS.items():
        for i in range(1, rinfo["engineers"] + 1):
            eng_id = f"ENG-{region_code}-{i:03d}"
            patch_code = f"{region_code}-P{((i - 1) % rinfo['patches']) + 1}"
            row = {
                "engineer_id": eng_id,
                "name": f"Engineer {emp_counter:04d}",
                "region_code": region_code,
                "region_name": rinfo["name"],
                "patch_code": patch_code,
                "employment_type": random.choices(EMPLOYMENT_TYPES, EMP_WEIGHTS)[0],
                "target_jobs_day": random.randint(3, 5),
            }
            engineers_rows.append(row)
            by_patch[patch_code].append(row)
            by_id[eng_id] = row
            emp_counter += 1

    return engineers_rows, by_patch, by_id


def _build_availability(engineers: list) -> tuple[list, dict]:
    rows = []
    by_key = {}
    leave_types = ["Available", "Annual Leave", "Sick", "Training", "Unavailable"]
    leave_weights = [0.82, 0.09, 0.04, 0.03, 0.02]

    for d in date_range(date(2025, 1, 1), date(2025, 12, 31)):
        is_weekend = d.weekday() >= 5
        for eng in engineers:
            if is_weekend and random.random() > 0.15:
                status = "Unavailable"
            else:
                status = random.choices(leave_types, leave_weights)[0]

            row = {
                "engineer_id": eng["engineer_id"],
                "region_code": eng["region_code"],
                "region_name": eng["region_name"],
                "patch_code": eng["patch_code"],
                "employment_type": eng["employment_type"],
                "avail_date": str(d),
                "year": d.year,
                "month": d.month,
                "week": week_of_year(d),
                "day_of_week": d.strftime("%A"),
                "status": status,
                "jobs_completed": 0,
                "jobs_target": eng["target_jobs_day"],
                "utilisation_pct": 0.0,
            }
            rows.append(row)
            by_key[(eng["engineer_id"], str(d))] = row

    return rows, by_key


def _choose_engineer(patch_engineers: list, availability: dict, d: date, assigned_counts: dict):
    available = []
    d_str = str(d)
    for eng in patch_engineers:
        row = availability.get((eng["engineer_id"], d_str))
        if not row or row["status"] != "Available":
            continue
        assigned = assigned_counts[(eng["engineer_id"], d_str)]
        if assigned < int(row["jobs_target"]) + 1:
            available.append((assigned, eng))

    if not available:
        return ""

    available.sort(key=lambda x: (x[0], x[1]["engineer_id"]))
    return available[0][1]["engineer_id"]


def _generate_master_operations(engineers_by_patch: dict, availability: dict, supplier_pool: list[str]) -> tuple[list, dict]:
    rows = []
    assigned_counts = defaultdict(int)
    job_counter = 1

    for d in date_range(date(2025, 1, 1), date(2026, 12, 31)):
        is_forecast = d.year == 2026
        sf = seasonal_factor(d)
        dof = day_of_week_factor(d)

        for region_code, rinfo in REGIONS.items():
            daily_target = rinfo["base_jobs"] / 22
            daily_volume = max(0, int(daily_target * sf * dof * gauss_noise(0.08)))

            for _ in range(daily_volume):
                meter = random.choices(METER_TYPES, METER_WEIGHTS)[0]
                job_type = random.choices(JOB_TYPES, JOB_TYPE_WEIGHTS)[0]
                channel = random.choices(CHANNELS, CHANNEL_WEIGHTS)[0]

                if is_forecast:
                    status = "Forecast"
                else:
                    roll = random.random()
                    if roll < 0.68:
                        status = "Completed"
                    elif roll < 0.82:
                        status = "Cancelled"
                    elif roll < 0.90:
                        status = "Aborted"
                    elif roll < 0.94:
                        status = "Booked"
                    else:
                        status = "Unbooked"

                patch_code = f"{region_code}-P{random.randint(1, rinfo['patches'])}"
                engineer_id = ""
                if status in ("Completed", "Aborted", "Booked"):
                    engineer_id = _choose_engineer(
                        engineers_by_patch[patch_code],
                        availability,
                        d,
                        assigned_counts,
                    )
                    if engineer_id:
                        assigned_counts[(engineer_id, str(d))] += 1

                booked_date = ""
                completed_date = ""
                if status in ("Completed", "Cancelled", "Aborted", "Booked"):
                    booked_dt = d - timedelta(days=random.randint(3, 21))
                    if booked_dt.year < d.year:
                        booked_dt = date(d.year, 1, 1)
                    booked_date = str(booked_dt)
                if status == "Completed":
                    completed_date = str(d)
                    if engineer_id:
                        availability[(engineer_id, str(d))]["jobs_completed"] += 1

                cancellation_reason = random.choice(CANCEL_REASONS) if status == "Cancelled" else ""
                abort_reason = random.choice(ABORT_REASONS) if status == "Aborted" else ""

                contacts_count = 0 if is_forecast else random.randint(1, 5)
                abandoned_contacts = 0 if is_forecast else (1 if random.random() < 0.10 else 0)
                avg_handle_mins = round(random.uniform(4.5, 12.5), 2)

                direct_cost = 0.0
                revenue = 0.0
                if status == "Completed":
                    revenue = REVENUE_MAP[job_type]
                    direct_cost = COST_MAP[job_type]
                elif status == "Aborted":
                    direct_cost = ABORT_COST

                removed_year_token = str(2000 + 24)
                while removed_year_token in f"{job_counter:07d}":
                    job_counter += 1

                rows.append({
                    "job_ref": f"IMSERV-{d.year}-{job_counter:07d}",
                    "supplier_name": supplier_pool[(job_counter - 1) % len(supplier_pool)],
                    "region_code": region_code,
                    "region_name": rinfo["name"],
                    "patch_code": patch_code,
                    "primary_channel": channel,
                    "meter_type": meter,
                    "job_type": job_type,
                    "status": status,
                    "requested_date": str(d),
                    "contact_date": str(d),
                    "booked_date": booked_date,
                    "completed_date": completed_date,
                    "engineer_id": engineer_id,
                    "contacts_count": contacts_count,
                    "abandoned_contacts": abandoned_contacts,
                    "avg_handle_mins": avg_handle_mins,
                    "cancellation_reason": cancellation_reason,
                    "abort_reason": abort_reason,
                    "revenue_gbp": round(revenue, 2),
                    "cost_gbp": round(direct_cost, 2),
                    "is_forecast": 1 if is_forecast else 0,
                })
                job_counter += 1

    for row in availability.values():
        if row["status"] == "Available":
            row["utilisation_pct"] = round(
                int(row["jobs_completed"]) / max(int(row["jobs_target"]), 1) * 100,
                1,
            )

    return rows, assigned_counts


def _derive_channel_volume(master_rows: list) -> list:
    daily = defaultdict(lambda: {
        "volume": 0,
        "bookings": 0,
        "cancellations": 0,
        "abandoned": 0,
        "handle_total": 0.0,
        "handle_count": 0,
        "region_name": "",
        "is_forecast": 0,
    })

    for row in master_rows:
        d = date.fromisoformat(row["contact_date"])
        key = (row["contact_date"], row["region_code"], row["primary_channel"])
        item = daily[key]
        item["region_name"] = row["region_name"]
        item["is_forecast"] = row["is_forecast"]
        item["volume"] += int(row["contacts_count"]) + int(row.get("abandoned_contacts", 0))
        item["bookings"] += 1 if row.get("booked_date") else 0
        item["cancellations"] += 1 if row["status"] == "Cancelled" else 0
        item["abandoned"] += int(row.get("abandoned_contacts", 0))
        item["handle_total"] += float(row["avg_handle_mins"])
        item["handle_count"] += 1

    rows = []
    for (contact_date, region_code, channel), item in sorted(daily.items()):
        d = date.fromisoformat(contact_date)
        rows.append({
            "contact_date": contact_date,
            "year": d.year,
            "month": d.month,
            "week": week_of_year(d),
            "day_of_week": d.strftime("%A"),
            "region_code": region_code,
            "region_name": item["region_name"],
            "channel": channel,
            "volume": item["volume"],
            "bookings": item["bookings"],
            "cancellations": item["cancellations"],
            "abandoned": item["abandoned"],
            "avg_handle_mins": round(item["handle_total"] / max(item["handle_count"], 1), 2),
            "is_forecast": item["is_forecast"],
        })
    return rows


def _derive_booking_journey(master_rows: list) -> list:
    weekly = defaultdict(lambda: defaultdict(int))
    meta = {}

    for row in master_rows:
        d = date.fromisoformat(row["requested_date"])
        ws = _week_start(d)
        key = (d.year, ws, row["region_code"])
        meta[key] = (row["region_name"], row["is_forecast"])
        weekly[key]["total_requests"] += 1
        weekly[key]["total_contacts"] += int(row["contacts_count"])
        weekly[key]["total_bookings"] += 1 if row.get("booked_date") else 0
        weekly[key]["total_cancellations"] += 1 if row["status"] == "Cancelled" else 0
        weekly[key]["total_aborts"] += 1 if row["status"] == "Aborted" else 0
        weekly[key]["total_completions"] += 1 if row["status"] == "Completed" else 0

    rows = []
    for (calendar_year, week_start, region_code), vals in sorted(weekly.items()):
        region_name, is_forecast = meta[(calendar_year, week_start, region_code)]
        requests = vals["total_requests"]
        contacts = vals["total_contacts"]
        completions = vals["total_completions"]
        rows.append({
            "week_start": str(week_start),
            "week_end": str(week_start + timedelta(days=6)),
            "year": calendar_year,
            "week_number": week_of_year(week_start),
            "region_code": region_code,
            "region_name": region_name,
            "total_requests": requests,
            "total_contacts": contacts,
            "avg_contacts_per_customer": round(contacts / max(requests, 1), 2),
            "total_bookings": vals["total_bookings"],
            "total_cancellations": vals["total_cancellations"],
            "total_aborts": vals["total_aborts"],
            "total_completions": completions,
            "completion_rate_pct": round(completions / max(requests, 1) * 100, 1),
            "is_forecast": is_forecast,
        })
    return rows


def _derive_financial_data(master_rows: list) -> list:
    monthly = defaultdict(lambda: defaultdict(float))
    meta = {}

    for row in master_rows:
        d = date.fromisoformat(row["requested_date"])
        key = (d.year, d.month, row["region_code"], row["job_type"])
        meta[key] = (row["region_name"], row["is_forecast"])
        monthly[key]["total_requests"] += 1
        monthly[key]["completions"] += 1 if row["status"] == "Completed" else 0
        monthly[key]["cancellations"] += 1 if row["status"] == "Cancelled" else 0
        monthly[key]["aborts"] += 1 if row["status"] == "Aborted" else 0
        monthly[key]["revenue_gbp"] += float(row["revenue_gbp"])
        monthly[key]["direct_cost_gbp"] += float(row["cost_gbp"])

    rows = []
    for (year, month, region_code, job_type), vals in sorted(monthly.items()):
        region_name, is_forecast = meta[(year, month, region_code, job_type)]
        direct_cost = round(vals["direct_cost_gbp"], 2)
        overhead = round(direct_cost * OVERHEAD_PCT, 2)
        total_cost = round(direct_cost + overhead, 2)
        revenue = round(vals["revenue_gbp"], 2)
        margin = round(revenue - total_cost, 2)
        completions = int(vals["completions"])
        rows.append({
            "year": year,
            "month": month,
            "month_name": _month_name(month),
            "quarter": f"Q{(month - 1) // 3 + 1}",
            "region_code": region_code,
            "region_name": region_name,
            "job_type": job_type,
            "total_requests": int(vals["total_requests"]),
            "completions": completions,
            "cancellations": int(vals["cancellations"]),
            "aborts": int(vals["aborts"]),
            "revenue_gbp": revenue,
            "direct_cost_gbp": direct_cost,
            "overhead_gbp": overhead,
            "total_cost_gbp": total_cost,
            "margin_gbp": margin,
            "margin_pct": round(margin / max(revenue, 1) * 100, 2),
            "cost_per_completion": round(total_cost / max(completions, 1), 2),
            "is_forecast": is_forecast,
        })
    return rows


def _derive_capacity_data(master_rows: list, availability_rows: list) -> list:
    demand = defaultdict(int)
    meta = {}
    for row in master_rows:
        d = date.fromisoformat(row["requested_date"])
        ws = _week_start(d)
        key = (d.year, ws, row["region_code"], row["patch_code"])
        if row.get("booked_date") or str(row.get("is_forecast", "0")) == "1":
            demand[key] += 1
        meta[key] = (row["region_name"], row["is_forecast"])

    capacity = defaultdict(lambda: {"engineer_days": 0, "capacity_jobs": 0, "region_name": ""})
    for row in availability_rows:
        d = date.fromisoformat(row["avail_date"])
        ws = _week_start(d)
        key = (d.year, ws, row["region_code"], row["patch_code"])
        capacity[key]["region_name"] = row["region_name"]
        if row["status"] == "Available":
            capacity[key]["engineer_days"] += 1
            capacity[key]["capacity_jobs"] += int(row["jobs_target"])

    all_keys = set(demand) | set(capacity)
    rows = []
    for calendar_year, week_start, region_code, patch_code in sorted(all_keys):
        if calendar_year > 2026:
            continue
        region_name, is_forecast = meta.get(
            (calendar_year, week_start, region_code, patch_code),
            (capacity[(calendar_year, week_start, region_code, patch_code)]["region_name"], 1 if calendar_year == 2026 else 0),
        )
        cap_jobs = int(capacity[(calendar_year, week_start, region_code, patch_code)]["capacity_jobs"])
        if calendar_year == 2026 and cap_jobs == 0:
            rinfo = REGIONS[region_code]
            engs_per_patch = max(1, rinfo["engineers"] // rinfo["patches"])
            cap_jobs = engs_per_patch * 4 * 5

        dem_jobs = int(demand[(calendar_year, week_start, region_code, patch_code)])
        util = round(dem_jobs / max(cap_jobs, 1) * 100, 1)
        rag = "Green" if util < 75 else ("Amber" if util < 90 else "Red")
        rows.append({
            "week_start": str(week_start),
            "year": calendar_year,
            "week_number": week_of_year(week_start),
            "region_code": region_code,
            "region_name": region_name,
            "patch_code": patch_code,
            "available_engineers": int(round(capacity[(calendar_year, week_start, region_code, patch_code)]["engineer_days"] / 5, 0)),
            "capacity_jobs": cap_jobs,
            "demand_jobs": dem_jobs,
            "gap_jobs": cap_jobs - dem_jobs,
            "utilisation_pct": util,
            "rag_status": rag,
            "is_forecast": is_forecast,
        })
    return rows


def generate_all():
    random.seed(RANDOM_SEED)
    print("\nIMSERV - Generating connected synthetic datasets...\n")

    engineers, engineers_by_patch, _ = _build_engineers()
    availability_rows, availability_by_key = _build_availability(engineers)
    suppliers = _load_suppliers()
    supplier_pool = _build_supplier_pool(suppliers)
    master_rows, _ = _generate_master_operations(engineers_by_patch, availability_by_key, supplier_pool)

    channel_volume = _derive_channel_volume(master_rows)
    booking_journey = _derive_booking_journey(master_rows)
    financial_data = _derive_financial_data(master_rows)
    capacity_demand = _derive_capacity_data(master_rows, availability_rows)

    write_csv("master_operations.csv", master_rows, list(master_rows[0].keys()))
    if SUPPLIERS_FILE.exists():
        write_csv("suppliers.csv", [{"supplier_name": s} for s in suppliers], ["supplier_name"])
    write_csv("channel_volume.csv", channel_volume, list(channel_volume[0].keys()))
    write_csv("booking_journey.csv", booking_journey, list(booking_journey[0].keys()))
    write_csv("engineers.csv", engineers, list(engineers[0].keys()))
    write_csv("engineer_availability.csv", availability_rows, list(availability_rows[0].keys()))
    write_csv("financial_data.csv", financial_data, list(financial_data[0].keys()))
    write_csv("capacity_demand.csv", capacity_demand, list(capacity_demand[0].keys()))

    manifest = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_of_truth": "master_operations.csv",
        "relationship_model": {
            "master_operations.csv": "Job-level ledger keyed by job_ref with supplier, region, patch, channel, engineer, status, dates, revenue, and cost.",
            "suppliers.csv": "Supplier dimension assigned to every request in master_operations.csv by supplier_name.",
            "channel_volume.csv": "Daily region/channel aggregation derived from master_operations.csv.",
            "booking_journey.csv": "Weekly funnel aggregation derived from master_operations.csv.",
            "financial_data.csv": "Monthly region/job-type P&L aggregation derived from master_operations.csv.",
            "capacity_demand.csv": "Weekly patch demand from master_operations.csv joined to engineer_availability.csv capacity.",
            "engineer_availability.csv": "Engineer-day table whose completed jobs are assigned from master_operations.csv.",
            "engineers.csv": "Engineer dimension joined by engineer_id.",
        },
        "files": [
            "master_operations.csv",
            "suppliers.csv",
            "channel_volume.csv",
            "booking_journey.csv",
            "engineers.csv",
            "engineer_availability.csv",
            "financial_data.csv",
            "capacity_demand.csv",
        ],
        "period": "2025-01-01 to 2026-12-31",
        "regions": list(REGIONS.keys()),
    }
    with open(INPUTS_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print("\n  OK  manifest.json")
    print("\nAll connected datasets generated successfully.\n")


if __name__ == "__main__":
    generate_all()
