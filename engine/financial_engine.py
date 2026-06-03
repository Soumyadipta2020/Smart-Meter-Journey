"""
Smart Meter Journey â€” Financial Scenario Planning Engine
Interactive simulation: job volume, meter type, region, engineer allocation,
productivity assumptions â†’ operational cost, revenue, margin, cost-per-job.
Mirrors DAA's Monte Carlo simulation architecture.
"""
import math
import random
import statistics
from collections import defaultdict

from engine.ingestion import (
    get_financial_data, to_int, to_float, safe_pct
)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

REVENUE_MAP  = {"NEW_INSTALL": 185.0, "EXCHANGE": 165.0, "REPAIR": 120.0, "REMOVAL": 90.0}
COST_MAP     = {"NEW_INSTALL":  95.0, "EXCHANGE":  82.0, "REPAIR":  65.0, "REMOVAL": 48.0}
ABORT_COST   = 38.0
OVERHEAD_PCT = 0.22   # 22% overhead on direct cost

JOB_TYPE_WEIGHTS = {"NEW_INSTALL": 0.35, "EXCHANGE": 0.40, "REPAIR": 0.18, "REMOVAL": 0.07}

# â”€â”€â”€ Core Calculations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _calculate_financials(
    job_volume: int,
    completion_rate: float,
    cancel_rate: float,
    abort_rate: float,
    revenue_uplift: float = 1.0,
    cost_uplift: float = 1.0,
    job_mix: dict = None,
) -> dict:
    """Core financial calculation given volume and rate assumptions."""
    if job_mix is None:
        job_mix = JOB_TYPE_WEIGHTS

    completions   = int(job_volume * completion_rate)
    cancellations = int(job_volume * cancel_rate)
    aborts        = int(job_volume * abort_rate)

    revenue    = 0.0
    direct_cost = 0.0
    job_type_contributions = []

    for jtype, weight in job_mix.items():
        vol     = int(completions * weight)
        rev     = vol * REVENUE_MAP.get(jtype, 150.0) * revenue_uplift
        cost    = vol * COST_MAP.get(jtype, 80.0)    * cost_uplift
        revenue     += rev
        direct_cost += cost
        job_type_contributions.append({
            "job_type":       jtype,
            "weight_pct":     int(round(weight * 100)),
            "jobs":           vol,
            "revenue_per_job": round(REVENUE_MAP.get(jtype, 150.0) * revenue_uplift, 2),
            "cost_per_job":    round(COST_MAP.get(jtype, 80.0) * cost_uplift, 2),
            "revenue":         round(rev, 2),
            "direct_cost":     round(cost, 2),
        })

    abort_cost_total = aborts * ABORT_COST * cost_uplift
    direct_cost += abort_cost_total
    overhead    = direct_cost * OVERHEAD_PCT
    total_cost  = direct_cost + overhead
    margin      = revenue - total_cost
    margin_pct  = safe_pct(margin, revenue, decimals=2)
    cpp         = round(total_cost / max(completions, 1), 2)

    return {
        "job_volume":       job_volume,
        "completions":      completions,
        "cancellations":    cancellations,
        "aborts":           aborts,
        "revenue_gbp":      round(revenue, 2),
        "direct_cost_gbp":  round(direct_cost, 2),
        "overhead_gbp":     round(overhead, 2),
        "total_cost_gbp":   round(total_cost, 2),
        "margin_gbp":       round(margin, 2),
        "margin_pct":       margin_pct,
        "cost_per_completion": cpp,
        "job_type_contributions": job_type_contributions,
        "abort_cost_total":       round(abort_cost_total, 2),
        "overhead_pct":           int(round(OVERHEAD_PCT * 100)),
    }


def _historical_financial_assumptions(region_code: str = None) -> dict:
    rows = get_financial_data()
    if region_code:
        rows = [r for r in rows if r.get("region_code") == region_code]
    rows = [r for r in rows if to_int(r.get("year")) == 2025]

    by_type = defaultdict(lambda: defaultdict(float))
    total = defaultdict(float)
    for r in rows:
        jt = r.get("job_type")
        requests = to_float(r.get("total_requests"))
        completions = to_float(r.get("completions"))
        cancellations = to_float(r.get("cancellations"))
        aborts = to_float(r.get("aborts"))
        revenue = to_float(r.get("revenue_gbp"))
        direct_cost = to_float(r.get("direct_cost_gbp"))

        for bucket in (by_type[jt], total):
            bucket["requests"] += requests
            bucket["completions"] += completions
            bucket["cancellations"] += cancellations
            bucket["aborts"] += aborts
            bucket["revenue"] += revenue
            bucket["direct_cost"] += direct_cost

    def rates(bucket, jt=None):
        completions = max(bucket["completions"], 1)
        return {
            "completion_rate": bucket["completions"] / max(bucket["requests"], 1),
            "cancel_rate": bucket["cancellations"] / max(bucket["requests"], 1),
            "abort_rate": bucket["aborts"] / max(bucket["requests"], 1),
            "revenue_per_completion": bucket["revenue"] / completions if bucket["revenue"] else REVENUE_MAP.get(jt, 150.0),
            "direct_cost_per_completion": bucket["direct_cost"] / completions if bucket["direct_cost"] else COST_MAP.get(jt, 80.0),
        }

    return {
        "default": rates(total),
        "by_type": {jt: rates(bucket, jt) for jt, bucket in by_type.items()},
    }


def _apply_2026_forecast_financials(rows: list, region_code: str = None) -> list:
    assumptions = _historical_financial_assumptions(region_code)
    result = []
    for row in rows:
        if to_int(row.get("year")) != 2026:
            result.append(row)
            continue

        jt = row.get("job_type")
        rates = assumptions["by_type"].get(jt, assumptions["default"])
        requests = to_int(row.get("total_requests"))
        completions = int(round(requests * rates["completion_rate"]))
        cancellations = int(round(requests * rates["cancel_rate"]))
        aborts = int(round(requests * rates["abort_rate"]))
        revenue = completions * rates["revenue_per_completion"]
        direct_cost = (completions * rates["direct_cost_per_completion"]) + (aborts * ABORT_COST)
        overhead = direct_cost * OVERHEAD_PCT
        total_cost = direct_cost + overhead
        margin = revenue - total_cost

        enriched = dict(row)
        enriched.update({
            "completions": completions,
            "cancellations": cancellations,
            "aborts": aborts,
            "revenue_gbp": round(revenue, 2),
            "direct_cost_gbp": round(direct_cost, 2),
            "overhead_gbp": round(overhead, 2),
            "total_cost_gbp": round(total_cost, 2),
            "margin_gbp": round(margin, 2),
            "margin_pct": safe_pct(margin, revenue, decimals=2),
            "cost_per_completion": round(total_cost / max(completions, 1), 2),
            "is_forecast": "1",
        })
        result.append(enriched)
    return result


# â”€â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_financial_kpis(region_code: str = None, year: int = 2025) -> dict:
    """
    Aggregated financial KPIs from historical data.

    Returns:
        dict with revenue, cost, margin, and profitability metrics
    """
    rows = get_financial_data()
    if region_code:
        rows = [r for r in rows if r["region_code"] == region_code]
    rows = [r for r in rows if to_int(r.get("year")) == year]
    if year == 2026:
        rows = _apply_2026_forecast_financials(rows, region_code)

    total_revenue   = sum(to_float(r["revenue_gbp"])        for r in rows)
    total_cost      = sum(to_float(r["total_cost_gbp"])     for r in rows)
    total_margin    = sum(to_float(r["margin_gbp"])         for r in rows)
    total_jobs      = sum(to_int(r["completions"])          for r in rows)
    total_requests  = sum(to_int(r["total_requests"])       for r in rows)
    total_cancellations = sum(to_int(r["cancellations"])    for r in rows)
    total_aborts        = sum(to_int(r["aborts"])           for r in rows)

    avg_cpp         = round(total_cost    / max(total_jobs, 1), 2)
    avg_margin_pct  = safe_pct(total_margin, total_revenue, decimals=2)

    # Monthly trend
    monthly: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        ym = f"{r.get('year')}-{int(r.get('month', 1)):02d}"
        monthly[ym]["revenue"]     += to_float(r["revenue_gbp"])
        monthly[ym]["cost"]        += to_float(r["total_cost_gbp"])
        monthly[ym]["margin"]      += to_float(r["margin_gbp"])
        monthly[ym]["completions"] += to_float(r["completions"])

    monthly_trend = []
    for ym in sorted(monthly.keys()):
        d = monthly[ym]
        monthly_trend.append({
            "month":       ym,
            "revenue":     round(d["revenue"], 2),
            "cost":        round(d["cost"], 2),
            "margin":      round(d["margin"], 2),
            "margin_pct":  safe_pct(d["margin"], d["revenue"], decimals=1),
            "completions": int(d["completions"]),
        })

    # By job type
    by_type: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        jt = r["job_type"]
        by_type[jt]["revenue"]     += to_float(r["revenue_gbp"])
        by_type[jt]["cost"]        += to_float(r["total_cost_gbp"])
        by_type[jt]["completions"] += to_float(r["completions"])

    job_type_breakdown = []
    for jt, d in by_type.items():
        job_type_breakdown.append({
            "job_type":    jt,
            "revenue":     round(d["revenue"], 2),
            "cost":        round(d["cost"], 2),
            "margin":      round(d["revenue"] - d["cost"], 2),
            "margin_pct":  safe_pct(d["revenue"] - d["cost"], d["revenue"], decimals=1),
            "completions": int(d["completions"]),
            "cpp":         round(d["cost"] / max(d["completions"], 1), 2),
        })
    job_type_breakdown.sort(key=lambda x: -x["revenue"])

    return {
        "total_revenue_gbp":  round(total_revenue, 2),
        "total_cost_gbp":     round(total_cost, 2),
        "total_margin_gbp":   round(total_margin, 2),
        "margin_pct":         avg_margin_pct,
        "total_completions":  total_jobs,
        "total_requests":     total_requests,
        "completion_rate":    safe_pct(total_jobs, total_requests),
        "cancellation_rate":  safe_pct(total_cancellations, total_requests),
        "abort_rate":         safe_pct(total_aborts, total_requests),
        "avg_cost_per_completion": avg_cpp,
        "monthly_trend":      monthly_trend,
        "job_type_breakdown": job_type_breakdown,
    }


def run_scenario(
    scenario_name: str,
    job_volume: int,
    completion_rate_pct: float = 68.0,
    cancel_rate_pct: float = 15.0,
    abort_rate_pct: float = 8.0,
    revenue_uplift_pct: float = 0.0,
    cost_uplift_pct: float = 0.0,
    engineer_count: int = 300,
    productivity_jobs_per_day: float = 4.0,
    region_code: str = None,
) -> dict:
    """
    Run a named financial scenario simulation.

    Parameters:
        scenario_name: Label for this scenario
        job_volume: Total jobs in period
        completion_rate_pct: % of jobs completed
        cancel_rate_pct: % cancelled
        abort_rate_pct: % aborted
        revenue_uplift_pct: Revenue price change (%)
        cost_uplift_pct: Cost change (%)
        engineer_count: FTE engineers
        productivity_jobs_per_day: Average jobs per engineer per day

    Returns:
        dict with full P&L, efficiency metrics, and waterfall data
    """
    cr  = completion_rate_pct / 100
    can = cancel_rate_pct     / 100
    ab  = abort_rate_pct      / 100
    ru  = 1 + revenue_uplift_pct / 100
    cu  = 1 + cost_uplift_pct    / 100

    result = _calculate_financials(
        job_volume=job_volume,
        completion_rate=cr,
        cancel_rate=can,
        abort_rate=ab,
        revenue_uplift=ru,
        cost_uplift=cu,
    )
    result["scenario_name"] = scenario_name
    result["engineer_count"] = engineer_count
    result["productivity"]   = productivity_jobs_per_day
    result["assumptions"] = {
        "abort_cost_per_job": ABORT_COST,
        "overhead_pct":       int(round(OVERHEAD_PCT * 100)),
        "revenue_uplift_pct": revenue_uplift_pct,
        "cost_uplift_pct":    cost_uplift_pct,
    }

    # Capacity check
    working_days  = 230  # approximate annual
    capacity_jobs = int(engineer_count * productivity_jobs_per_day * working_days)
    result["capacity_jobs"] = capacity_jobs
    result["capacity_gap"]  = capacity_jobs - result["completions"]
    result["capacity_rag"]  = (
        "Red"   if result["completions"] > capacity_jobs else
        "Amber" if result["completions"] > capacity_jobs * 0.90 else
        "Green"
    )

    # Waterfall data for chart
    base = _calculate_financials(
        job_volume=job_volume, completion_rate=0.68,
        cancel_rate=0.15, abort_rate=0.08
    )
    result["waterfall"] = [
        {"label": "Base Revenue",        "value":  base["revenue_gbp"],     "type": "base"},
        {"label": "Revenue Change",       "value":  result["revenue_gbp"] - base["revenue_gbp"], "type": "delta"},
        {"label": "Direct Cost",          "value": -result["direct_cost_gbp"], "type": "cost"},
        {"label": "Overhead",             "value": -result["overhead_gbp"],    "type": "cost"},
        {"label": "Net Margin",           "value":  result["margin_gbp"],      "type": "total"},
    ]

    return result


def compare_scenarios(scenarios: list) -> dict:
    """
    Compare multiple named scenarios side-by-side.

    Parameters:
        scenarios: list of scenario param dicts (same keys as run_scenario)

    Returns:
        dict with comparison table, best/worst scenario, and recommendation
    """
    results = []
    for s in scenarios:
        res = run_scenario(**s)
        results.append(res)

    best  = max(results, key=lambda x: x["margin_pct"])
    worst = min(results, key=lambda x: x["margin_pct"])

    return {
        "scenarios":           results,
        "best_scenario":       best["scenario_name"],
        "worst_scenario":      worst["scenario_name"],
        "margin_range":        [worst["margin_pct"], best["margin_pct"]],
        "recommendation": (
            f"Scenario '{best['scenario_name']}' delivers highest margin at "
            f"{best['margin_pct']}% (Â£{best['margin_gbp']:,.0f}). "
            f"Consider applying its parameters regionally."
        ),
    }


def get_forecast_profitability(region_code: str = None) -> dict:
    """
    2026 forecast profitability based on 2026 forecast demand.

    Returns:
        dict with monthly P&L forecast for 2026
    """
    forecast_kpis = get_financial_kpis(region_code, year=2026)
    monthly_rows = forecast_kpis["monthly_trend"]

    if not monthly_rows:
        return {"monthly_forecast": [], "annual_summary": {}}

    monthly_forecast = []
    for m in monthly_rows:
        monthly_forecast.append({
            "month":       m["month"],
            "revenue":     m["revenue"],
            "cost":        m["cost"],
            "margin":      m["margin"],
            "margin_pct":  m["margin_pct"],
            "is_forecast": True,
        })

    annual = {
        "revenue":     sum(m["revenue"]  for m in monthly_forecast),
        "cost":        sum(m["cost"]     for m in monthly_forecast),
        "margin":      sum(m["margin"]   for m in monthly_forecast),
        "margin_pct":  safe_pct(
            sum(m["margin"] for m in monthly_forecast),
            sum(m["revenue"] for m in monthly_forecast),
            decimals=2
        ),
    }

    return {
        "monthly_forecast": monthly_forecast,
        "annual_summary":   {k: round(v, 2) for k, v in annual.items()},
        "assumptions": {
            "source": "2026 forecast demand with 2025 realised conversion and cost rates",
        },
    }
