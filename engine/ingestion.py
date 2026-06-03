"""
Smart Meter Journey â€” Data Ingestion Layer
Loads and caches CSV datasets; provides typed accessor functions.
Mirrors DAA-Project's lazy-loading cache pattern.
"""
import csv
import os
from pathlib import Path

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BASE_DIR   = Path(__file__).resolve().parent.parent
INPUTS_DIR = BASE_DIR / "data" / "inputs"

# â”€â”€â”€ Module-level caches (populated on first access) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_JOBS_CACHE              = None
_CHANNEL_CACHE           = None
_JOURNEY_CACHE           = None
_ENGINEERS_CACHE         = None
_AVAILABILITY_CACHE      = None
_FINANCIAL_CACHE         = None
_CAPACITY_CACHE          = None
_FORECAST_BASELINE_CACHE = None

DATASET_FILES = [
    "master_operations.csv",
    "suppliers.csv",
    "channel_volume.csv",
    "booking_journey.csv",
    "engineers.csv",
    "engineer_availability.csv",
    "financial_data.csv",
    "capacity_demand.csv",
    "forecast_baseline_2025.csv",
]
_DATA_HEALTH_CACHE = {}

def _cache_large_datasets() -> bool:
    """Keep large CSVs uncached by default on constrained hosts like Render."""
    return os.getenv("SMJ_CACHE_LARGE_DATASETS", "").lower() == "true"


def _load_csv(filename: str) -> list:
    """Load a CSV from inputs directory, filter empty rows."""
    path = INPUTS_DIR / filename
    if not path.exists():
        _DATA_HEALTH_CACHE[filename] = {"exists": False, "rows": 0, "size_bytes": 0}
        return []
    with open(path, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if any(v and v.strip() for v in r.values())]
    _DATA_HEALTH_CACHE[filename] = {
        "exists": True,
        "rows": len(rows),
        "size_bytes": path.stat().st_size,
    }
    return rows


def iter_csv(filename: str):
    """Yield non-empty CSV rows without materializing the whole file."""
    path = INPUTS_DIR / filename
    if not path.exists():
        _DATA_HEALTH_CACHE[filename] = {"exists": False, "rows": 0, "size_bytes": 0}
        return

    count = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if any(v and v.strip() for v in row.values()):
                count += 1
                yield row

    _DATA_HEALTH_CACHE[filename] = {
        "exists": True,
        "rows": count,
        "size_bytes": path.stat().st_size,
    }


def _count_csv_rows(filename: str) -> int:
    """Count CSV rows without materializing them as dictionaries."""
    path = INPUTS_DIR / filename
    if not path.exists():
        _DATA_HEALTH_CACHE[filename] = {"exists": False, "rows": 0, "size_bytes": 0}
        return 0
    with open(path, encoding="utf-8-sig") as f:
        count = max(sum(1 for _ in f) - 1, 0)
    _DATA_HEALTH_CACHE[filename] = {
        "exists": True,
        "rows": count,
        "size_bytes": path.stat().st_size,
    }
    return count


# â”€â”€â”€ Public Accessors â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_jobs(force_reload: bool = False) -> list:
    global _JOBS_CACHE
    master_path = INPUTS_DIR / "master_operations.csv"
    filename = "master_operations.csv" if master_path.exists() else "smart_meter_jobs.csv"
    if not _cache_large_datasets():
        return _load_csv(filename)
    if _JOBS_CACHE is None or force_reload:
        _JOBS_CACHE = _load_csv(filename)
    return _JOBS_CACHE


def iter_jobs():
    """Stream the job ledger row-by-row for memory-constrained routes."""
    master_path = INPUTS_DIR / "master_operations.csv"
    filename = "master_operations.csv" if master_path.exists() else "smart_meter_jobs.csv"
    yield from iter_csv(filename)


def get_channel_volume(force_reload: bool = False) -> list:
    global _CHANNEL_CACHE
    if _CHANNEL_CACHE is None or force_reload:
        _CHANNEL_CACHE = _load_csv("channel_volume.csv")
    return _CHANNEL_CACHE


def iter_channel_volume():
    """Stream channel volume rows for lightweight first-page routes."""
    yield from iter_csv("channel_volume.csv")


def get_booking_journey(force_reload: bool = False) -> list:
    global _JOURNEY_CACHE
    if _JOURNEY_CACHE is None or force_reload:
        _JOURNEY_CACHE = _load_csv("booking_journey.csv")
    return _JOURNEY_CACHE


def get_engineers(force_reload: bool = False) -> list:
    global _ENGINEERS_CACHE
    if _ENGINEERS_CACHE is None or force_reload:
        _ENGINEERS_CACHE = _load_csv("engineers.csv")
    return _ENGINEERS_CACHE


def get_engineer_availability(force_reload: bool = False) -> list:
    global _AVAILABILITY_CACHE
    if not _cache_large_datasets():
        return _load_csv("engineer_availability.csv")
    if _AVAILABILITY_CACHE is None or force_reload:
        _AVAILABILITY_CACHE = _load_csv("engineer_availability.csv")
    return _AVAILABILITY_CACHE


def iter_engineer_availability():
    """Stream engineer availability without creating a large list of dicts."""
    yield from iter_csv("engineer_availability.csv")


def get_financial_data(force_reload: bool = False) -> list:
    global _FINANCIAL_CACHE
    if _FINANCIAL_CACHE is None or force_reload:
        _FINANCIAL_CACHE = _load_csv("financial_data.csv")
    return _FINANCIAL_CACHE


def get_capacity_demand(force_reload: bool = False) -> list:
    global _CAPACITY_CACHE
    if _CAPACITY_CACHE is None or force_reload:
        _CAPACITY_CACHE = _load_csv("capacity_demand.csv")
    return _CAPACITY_CACHE


def get_forecast_baseline_2025(force_reload: bool = False) -> list:
    global _FORECAST_BASELINE_CACHE
    if _FORECAST_BASELINE_CACHE is None or force_reload:
        _FORECAST_BASELINE_CACHE = _load_csv("forecast_baseline_2025.csv")
    return _FORECAST_BASELINE_CACHE


def preload_all_data(force_reload: bool = False) -> dict:
    """Warm CSV caches. Large datasets are counted, not cached, by default."""
    large_counts = {}
    if not _cache_large_datasets():
        large_counts = {
            "master_operations.csv": _count_csv_rows("master_operations.csv"),
            "engineer_availability.csv": _count_csv_rows("engineer_availability.csv"),
        }
    else:
        large_counts = {
            "master_operations.csv": len(get_jobs(force_reload)),
            "engineer_availability.csv": len(get_engineer_availability(force_reload)),
        }

    return {
        **large_counts,
        "channel_volume.csv": len(get_channel_volume(force_reload)),
        "booking_journey.csv": len(get_booking_journey(force_reload)),
        "engineers.csv": len(get_engineers(force_reload)),
        "financial_data.csv": len(get_financial_data(force_reload)),
        "capacity_demand.csv": len(get_capacity_demand(force_reload)),
        "forecast_baseline_2025.csv": len(get_forecast_baseline_2025(force_reload)),
    }


def clear_data_caches() -> dict:
    """Drop in-memory CSV caches so constrained instances can reclaim RAM."""
    global _JOBS_CACHE, _CHANNEL_CACHE, _JOURNEY_CACHE, _ENGINEERS_CACHE
    global _AVAILABILITY_CACHE, _FINANCIAL_CACHE, _CAPACITY_CACHE
    global _FORECAST_BASELINE_CACHE

    _JOBS_CACHE = None
    _CHANNEL_CACHE = None
    _JOURNEY_CACHE = None
    _ENGINEERS_CACHE = None
    _AVAILABILITY_CACHE = None
    _FINANCIAL_CACHE = None
    _CAPACITY_CACHE = None
    _FORECAST_BASELINE_CACHE = None
    return data_health()


# â”€â”€â”€ Filter Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def filter_by(rows: list, **kwargs) -> list:
    """Filter rows by exact field match. Case-insensitive for string values."""
    result = rows
    for key, val in kwargs.items():
        if val is None:
            continue
        val_str = str(val).lower()
        result = [r for r in result if str(r.get(key, "")).lower() == val_str]
    return result


def filter_date_range(rows: list, date_field: str, start: str, end: str) -> list:
    """Filter rows where date_field falls within [start, end] (ISO strings)."""
    return [
        r for r in rows
        if start <= r.get(date_field, "")[:10] <= end
    ]


def to_int(val, default: int = 0) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def to_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_pct(numerator, denominator, decimals: int = 1) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, decimals)


# â”€â”€â”€ Data Health Check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def data_health() -> dict:
    """Return file presence plus cached row counts without scanning CSVs."""
    result = {}
    for f in DATASET_FILES:
        path = INPUTS_DIR / f
        exists = path.exists()
        cached = _DATA_HEALTH_CACHE.get(f, {})
        result[f] = {
            "exists": exists,
            "rows": cached.get("rows"),
            "size_bytes": path.stat().st_size if exists else 0,
        }
    return result
