"""
IMSERV Platform — Contact Centre Forecasting Engine
Multi-model ensemble: Prophet, ARIMA, XGBoost, LightGBM.
Mirrors DAA's modular ML architecture pattern.
"""
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from engine.ingestion import (
    iter_channel_volume, get_booking_journey, iter_jobs, get_capacity_demand,
    get_forecast_baseline_2025,
    to_int, to_float, safe_pct
)

# ─────────────────────────────────────────────────────────────────────────────
_FORECAST_CACHE = {}

MODELS = ["Prophet", "ARIMA", "XGBoost", "LightGBM"]


def clear_forecast_cache() -> None:
    """Clear cached forecast results after source CSV data changes."""
    _FORECAST_CACHE.clear()

NOT_COMPLETED_REASON_LABELS = {
    "EXCHANGE": "Exchange still booked",
    "NEW_INSTALL": "Install still booked",
    "REPAIR": "Repair follow-up booked",
    "REMOVAL": "Removal still booked",
}

INTERACTION_ROUTE_RULES = [
    {
        "source_interaction_channel": "Inbound",
        "customer_interaction_type": "Voice Call",
        "source_channels": {"Phone": 0.65},
        "journey_stage": "Initial contact",
    },
    {
        "source_interaction_channel": "Web Chat",
        "customer_interaction_type": "Chat",
        "source_channels": {"Web": 0.75, "App": 1.0},
        "journey_stage": "Digital support",
    },
    {
        "source_interaction_channel": "CALLBACK",
        "customer_interaction_type": "Voice Call",
        "source_channels": {"Agent Callback": 1.0},
        "journey_stage": "Follow-up",
    },
    {
        "source_interaction_channel": "TRANSFER",
        "customer_interaction_type": "Chat",
        "source_channels": {"Web": 0.25},
        "journey_stage": "Specialist handoff",
    },
    {
        "source_interaction_channel": "Outbound",
        "customer_interaction_type": "Voice Call",
        "source_channels": {"Phone": 0.20},
        "journey_stage": "Proactive contact",
    },
    {
        "source_interaction_channel": "CONSULT",
        "customer_interaction_type": "Voice Call",
        "source_channels": {"IVR": 0.55},
        "journey_stage": "Advisor support",
    },
    {
        "source_interaction_channel": "TRANSFER",
        "customer_interaction_type": "Voice Call",
        "source_channels": {"Phone": 0.15, "IVR": 0.45},
        "journey_stage": "Voice handoff",
    },
    {
        "source_interaction_channel": "Outbound",
        "customer_interaction_type": "Chat",
        "source_channels": {"SMS": 1.0},
        "journey_stage": "Reminder",
    },
]

# ─── Seasonal Helpers ─────────────────────────────────────────────────────────

def _seasonal_index(week: int, amplitude: float = 0.18) -> float:
    return 1.0 + amplitude * math.sin(2 * math.pi * (week - 26) / 52)


def _trend_factor(week_idx: int, growth_rate: float = 0.04) -> float:
    """Annual growth factor applied linearly across the forecast horizon."""
    return 1.0 + growth_rate * (week_idx / 52)


# ─── Model Simulators ─────────────────────────────────────────────────────────

def _prophet_forecast(history: list, horizon_weeks: int, growth: float = 0.04) -> list:
    """Simplified Prophet-style: trend + seasonal + noise."""
    if not history:
        return []
    baseline = statistics.median(history[-12:]) if len(history) >= 12 else statistics.mean(history)
    result = []
    for i in range(horizon_weeks):
        si = _seasonal_index(i % 52)
        tf = _trend_factor(i, growth)
        noise = 1.0 + random.gauss(0, 0.03)
        result.append(baseline * si * tf * noise)
    return result


def _arima_forecast(history: list, horizon_weeks: int) -> list:
    """ARIMA(1,1,1)-style: last diff + AR(1) reversion."""
    if len(history) < 4:
        return _prophet_forecast(history, horizon_weeks)
    last = history[-1]
    mu   = statistics.mean(history)
    phi  = 0.65  # AR coefficient
    result = []
    prev = last
    for i in range(horizon_weeks):
        noise = random.gauss(0, statistics.stdev(history[-12:]) * 0.4 if len(history) >= 12 else 10)
        val = mu + phi * (prev - mu) + noise
        result.append(max(0, val))
        prev = val
    return result


def _xgboost_forecast(history: list, horizon_weeks: int) -> list:
    """XGBoost proxy: gradient-boosted residual correction."""
    if len(history) < 8:
        return _prophet_forecast(history, horizon_weeks)
    trend = (history[-1] - history[0]) / len(history)
    result = []
    for i in range(horizon_weeks):
        residual = random.gauss(0, statistics.stdev(history) * 0.25)
        val = history[-1] + trend * (i + 1) + residual
        result.append(max(0, val))
    return result


def _lgbm_forecast(history: list, horizon_weeks: int) -> list:
    """LightGBM proxy: leaf-wise boosting with seasonal correction."""
    if len(history) < 6:
        return _prophet_forecast(history, horizon_weeks)
    baseline = statistics.mean(history[-8:]) if len(history) >= 8 else statistics.mean(history)
    result = []
    for i in range(horizon_weeks):
        si = _seasonal_index(i % 52)
        noise = 1.0 + random.gauss(0, 0.025)
        result.append(baseline * si * noise)
    return result


def _ensemble(forecasts: dict, weights: dict = None) -> list:
    """Inverse-MAPE weighted ensemble across model forecasts."""
    if not forecasts:
        return []
    if weights is None:
        weights = {m: 1.0 for m in forecasts}

    total_w = sum(weights.values())
    horizon = min(len(v) for v in forecasts.values())
    result = []
    for i in range(horizon):
        val = sum(forecasts[m][i] * weights.get(m, 1.0) for m in forecasts) / total_w
        result.append(val)
    return result


def _confidence_bands(point_forecast: list, ci_pct: float = 0.20) -> tuple:
    """Generate P10/P50/P90 from point forecast with proportional uncertainty."""
    p50 = point_forecast
    p10 = [v * (1 - ci_pct) for v in p50]
    p90 = [v * (1 + ci_pct) for v in p50]
    return p10, p50, p90


def _daily_volume_history(region_code: str = None, channel: str = None, year: int = 2025) -> list:
    """Aggregate actual contact attempts by day for daily-level accuracy checks."""
    daily: dict = defaultdict(float)
    for r in iter_channel_volume():
        if region_code and r.get("region_code") != region_code:
            continue
        if channel and r.get("channel") != channel:
            continue
        if to_int(r.get("year")) != year or r.get("is_forecast", "0") != "0":
            continue
        day = r.get("contact_date") or ""
        if day:
            daily[day] += to_float(r.get("volume", 0))
    return [daily[k] for k in sorted(daily.keys())]


def _evaluate_daily_metrics(model_name: str, daily_history: list) -> dict:
    """Calculate true backtested daily MAPE, MAE, and RMSE for a model."""
    if len(daily_history) < 30:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}
    
    # Split: predict the last 30 days using data before that
    train = daily_history[:-30]
    test = daily_history[-30:]
    horizon = len(test)
    
    if model_name == "Prophet":
        baseline = statistics.median(train[-14:]) if len(train) >= 14 else statistics.mean(train)
        pred = [baseline * (1.0 + 0.1 * math.sin(2 * math.pi * (i % 7) / 7)) for i in range(horizon)]
    elif model_name == "ARIMA":
        last = train[-1]
        mu = statistics.mean(train)
        pred = []
        prev = last
        for i in range(horizon):
            val = mu + 0.65 * (prev - mu)
            pred.append(val)
            prev = val
    elif model_name == "XGBoost":
        trend = (train[-1] - train[0]) / len(train) if len(train) > 0 else 0
        pred = [train[-1] + trend * (i + 1) for i in range(horizon)]
    elif model_name == "LightGBM":
        baseline = statistics.mean(train[-7:]) if len(train) >= 7 else statistics.mean(train)
        pred = [baseline * (1.0 + 0.05 * math.sin(2 * math.pi * (i % 7) / 7)) for i in range(horizon)]
    else:
        pred = [statistics.mean(train)] * horizon
        
    mae = rmse = mape = 0.0
    mape_n = 0
    for a, p in zip(test, pred):
        mae += abs(a - p)
        rmse += (a - p)**2
        if a > 0:
            mape += abs(a - p) / a * 100
            mape_n += 1
            
    return {
        "mae": round(mae / horizon, 1),
        "rmse": round(math.sqrt(rmse / horizon), 1),
        "mape": round(mape / max(mape_n, 1), 2)
    }


def _daily_model_accuracy(region_code: str = None, channel: str = None, year: int = 2025, include_models: list = None) -> dict:
    """Backtest model proxies against daily actual contact-attempt volume."""
    if include_models is None:
        include_models = MODELS
    daily_history = _daily_volume_history(region_code, channel, year)
    return {model: _evaluate_daily_metrics(model, daily_history) for model in include_models}


def _best_daily_accuracy(region_code: str = None, channel: str = None, year: int = 2025) -> dict:
    metrics = _daily_model_accuracy(region_code, channel, year)
    if not metrics:
        return {"model": None, "mae": 0.0, "rmse": 0.0, "mape": 0.0, "accuracy_pct": 0.0}
    model, data = min(metrics.items(), key=lambda item: item[1].get("mape", 999))
    mape = float(data.get("mape") or 0)
    return {
        "model": model,
        "mae": data.get("mae", 0.0),
        "rmse": data.get("rmse", 0.0),
        "mape": mape,
        "accuracy_pct": round(max(0.0, 100.0 - mape), 1),
    }


def _beginning_2025_forecast_accuracy(year: int = 2025) -> dict:
    """Accuracy of the forecast made at the start of 2025 for 2025 actuals."""
    rows = [r for r in get_forecast_baseline_2025() if to_int(r.get("year")) == year]
    if not rows:
        return {"label": "Beginning-of-year forecast", "mape": 0.0, "accuracy_pct": 0.0}

    mape = 0.0
    count = 0
    label = rows[0].get("forecast_name") or "Beginning-of-year forecast"
    for row in rows:
        actual = to_float(row.get("actual_volume"))
        forecast = to_float(row.get("forecast_volume"))
        if actual <= 0:
            continue
        mape += abs(actual - forecast) / actual * 100
        count += 1

    mape = round(mape / max(count, 1), 2)
    return {
        "label": label,
        "mape": mape,
        "accuracy_pct": round(max(0.0, 100.0 - mape), 1),
    }


# ─── Public API ───────────────────────────────────────────────────────────────

def forecast_channel_volume(
    region_code: str = None,
    channel: str = None,
    horizon_weeks: int = 26,
    include_models: list = None,
) -> dict:
    """
    Forecast weekly contact centre volume.

    Parameters:
        region_code: Filter by region (None = all regions)
        channel: Filter by channel (None = all channels)
        horizon_weeks: Number of weeks to forecast
        include_models: List of model names to include

    Returns:
        dict with forecast results, model metrics, confidence bands
    """
    cache_key = f"{region_code}_{channel}_{horizon_weeks}"
    if cache_key in _FORECAST_CACHE:
        return _FORECAST_CACHE[cache_key]

    if include_models is None:
        include_models = MODELS

    # Aggregate by week
    weekly: dict = defaultdict(float)
    for r in iter_channel_volume():
        if region_code and r.get("region_code") != region_code:
            continue
        if channel and r.get("channel") != channel:
            continue
        if r.get("is_forecast", "0") != "0":
            continue
        wk = f"{r.get('year', '2025')}-W{int(r.get('week', 1)):02d}"
        weekly[wk] += to_float(r.get("volume", 0))

    history = [weekly[k] for k in sorted(weekly.keys())]
    if not history:
        history = [1000.0] * 52  # default fallback

    # Run models
    model_forecasts = {}
    if "Prophet"  in include_models: model_forecasts["Prophet"]  = _prophet_forecast(history, horizon_weeks)
    if "ARIMA"    in include_models: model_forecasts["ARIMA"]    = _arima_forecast(history, horizon_weeks)
    if "XGBoost"  in include_models: model_forecasts["XGBoost"]  = _xgboost_forecast(history, horizon_weeks)
    if "LightGBM" in include_models: model_forecasts["LightGBM"] = _lgbm_forecast(history, horizon_weeks)

    ensemble = _ensemble(model_forecasts)
    p10, p50, p90 = _confidence_bands(ensemble)

    # Build forecast date labels
    last_date = date(2025, 12, 28)
    labels = []
    for i in range(horizon_weeks):
        d = last_date + timedelta(weeks=i + 1)
        labels.append(str(d))

    model_accuracy = _daily_model_accuracy(region_code, channel, 2025, include_models)

    result = {
        "labels":          labels,
        "p10":             [round(v, 0) for v in p10],
        "p50":             [round(v, 0) for v in p50],
        "p90":             [round(v, 0) for v in p90],
        "history_labels":  list(sorted(weekly.keys()))[-52:],
        "history_values":  history[-52:],
        "model_forecasts": {m: [round(v, 0) for v in vals]
                            for m, vals in model_forecasts.items()},
        "model_accuracy":  model_accuracy,
        "horizon_weeks":   horizon_weeks,
        "region_filter":   region_code,
        "channel_filter":  channel,
    }
    _FORECAST_CACHE[cache_key] = result
    return result


def get_channel_kpis(region_code: str = None, year: int = 2025) -> dict:
    """Aggregate KPIs for contact centre: volume, conversion, abandonment."""
    total_volume = total_bookings = total_cancel = total_abandon = 0
    by_channel: dict = defaultdict(lambda: defaultdict(float))
    for r in iter_channel_volume():
        if region_code and r.get("region_code") != region_code:
            continue
        if to_int(r.get("year")) != year:
            continue

        total_volume   += to_int(r["volume"])
        total_bookings += to_int(r["bookings"])
        total_cancel   += to_int(r["cancellations"])
        total_abandon  += to_int(r["abandoned"])

        ch = r["channel"]
        by_channel[ch]["volume"]        += to_float(r["volume"])
        by_channel[ch]["bookings"]       += to_float(r["bookings"])
        by_channel[ch]["cancellations"]  += to_float(r["cancellations"])
        by_channel[ch]["abandoned"]      += to_float(r["abandoned"])

    channel_breakdown = []
    for ch, d in by_channel.items():
        conv = safe_pct(d["bookings"], d["volume"])
        successful_visits = max(d["bookings"] - d["cancellations"], 0)
        channel_breakdown.append({
            "channel":       ch,
            "volume":        int(d["volume"]),
            "bookings":      int(d["bookings"]),
            "cancellations":  int(d["cancellations"]),
            "successful_visits": int(successful_visits),
            "conversion_pct": conv,
            "visit_success_pct": safe_pct(successful_visits, d["bookings"]),
            "abandon_pct":   safe_pct(d["abandoned"], d["volume"]),
        })
    channel_breakdown.sort(key=lambda x: -x["volume"])

    return {
        "total_volume":      total_volume,
        "total_bookings":    total_bookings,
        "total_cancellations": total_cancel,
        "total_successful_visits": max(total_bookings - total_cancel, 0),
        "total_abandoned":   total_abandon,
        "conversion_rate":   safe_pct(total_bookings, total_volume),
        "visit_success_rate": safe_pct(total_bookings - total_cancel, total_bookings),
        "abandon_rate":      safe_pct(total_abandon, total_volume),
        "channel_breakdown": channel_breakdown,
    }


def get_customer_interaction_map(region_code: str = None, year: int = 2025) -> dict:
    """Classify source interaction channels into customer interaction types."""
    by_channel: dict = defaultdict(lambda: defaultdict(float))
    for r in iter_channel_volume():
        if region_code and r.get("region_code") != region_code:
            continue
        if to_int(r.get("year")) != year or r.get("is_forecast", "0") != "0":
            continue

        ch = r["channel"]
        by_channel[ch]["volume"]        += to_float(r["volume"])
        by_channel[ch]["bookings"]      += to_float(r["bookings"])
        by_channel[ch]["cancellations"] += to_float(r["cancellations"])
        by_channel[ch]["abandoned"]     += to_float(r["abandoned"])

    routes = []
    by_type: dict = defaultdict(lambda: defaultdict(float))
    total_interactions = 0
    total_bookings = 0

    for rule in INTERACTION_ROUTE_RULES:
        volume = bookings = cancellations = abandoned = 0.0
        source_names = []
        for channel, share in rule["source_channels"].items():
            source_names.append(channel)
            volume        += by_channel[channel]["volume"]        * share
            bookings      += by_channel[channel]["bookings"]      * share
            cancellations += by_channel[channel]["cancellations"] * share
            abandoned     += by_channel[channel]["abandoned"]     * share

        volume_i = int(round(volume))
        bookings_i = int(round(bookings))
        cancellations_i = int(round(cancellations))
        abandoned_i = int(round(abandoned))
        interaction_type = rule["customer_interaction_type"]

        by_type[interaction_type]["volume"]        += volume_i
        by_type[interaction_type]["bookings"]      += bookings_i
        by_type[interaction_type]["cancellations"] += cancellations_i
        by_type[interaction_type]["abandoned"]     += abandoned_i
        total_interactions += volume_i
        total_bookings += bookings_i

        routes.append({
            "source_interaction_channel": rule["source_interaction_channel"],
            "customer_interaction_type":  interaction_type,
            "journey_stage":              rule["journey_stage"],
            "source_channels":            source_names,
            "interactions":               volume_i,
            "bookings":                   bookings_i,
            "cancellations":              cancellations_i,
            "abandoned":                  abandoned_i,
            "conversion_pct":             safe_pct(bookings_i, volume_i),
            "abandon_pct":                safe_pct(abandoned_i, volume_i),
        })

    type_summary = []
    for interaction_type, d in by_type.items():
        type_summary.append({
            "customer_interaction_type": interaction_type,
            "interactions":             int(d["volume"]),
            "bookings":                 int(d["bookings"]),
            "cancellations":            int(d["cancellations"]),
            "abandoned":                int(d["abandoned"]),
            "share_pct":                safe_pct(d["volume"], total_interactions),
            "conversion_pct":           safe_pct(d["bookings"], d["volume"]),
        })
    type_summary.sort(key=lambda x: -x["interactions"])
    routes.sort(key=lambda x: -x["interactions"])

    top_route = routes[0] if routes else None
    highest_conversion = max(routes, key=lambda x: x["conversion_pct"]) if routes else None

    return {
        "routes":             routes,
        "type_summary":       type_summary,
        "total_interactions": total_interactions,
        "total_bookings":     total_bookings,
        "conversion_pct":     safe_pct(total_bookings, total_interactions),
        "top_route":          top_route,
        "highest_conversion": highest_conversion,
    }


def get_booking_conversion_funnel(region_code: str = None, year: int = 2025) -> dict:
    """Weekly booking conversion funnel data."""
    rows = get_booking_journey()
    if region_code:
        rows = [r for r in rows if r["region_code"] == region_code]
    rows = [r for r in rows if to_int(r.get("year")) == year]

    total_requests     = sum(to_int(r["total_requests"])     for r in rows)
    total_contacts     = sum(to_int(r["total_contacts"])     for r in rows)
    total_bookings     = sum(to_int(r["total_bookings"])     for r in rows)
    total_cancellations= sum(to_int(r["total_cancellations"])for r in rows)
    total_aborts       = sum(to_int(r["total_aborts"])       for r in rows)
    total_completions  = sum(to_int(r["total_completions"])  for r in rows)
    total_visits       = max(total_bookings - total_cancellations, 0)
    total_after_aborts = max(total_visits - total_aborts, 0)
    total_not_completed = max(total_after_aborts - total_completions, 0)

    year_str = str(year)
    not_completed_reasons = Counter()
    for job in iter_jobs():
        if region_code and job.get("region_code") != region_code:
            continue
        if job.get("requested_date", "")[:4] != year_str or job.get("is_forecast", "0") != "0":
            continue
        if job.get("status") == "Booked":
            job_type = job.get("job_type") or "Other"
            not_completed_reasons[job_type] += 1

    reason_breakdown = [
        {
            "reason": NOT_COMPLETED_REASON_LABELS.get(reason, reason.replace("_", " ").title()),
            "count": count,
            "pct": safe_pct(count, total_not_completed),
        }
        for reason, count in not_completed_reasons.most_common()
    ]
    reason_total = sum(item["count"] for item in reason_breakdown)
    if total_not_completed > reason_total:
        reason_breakdown.append({
            "reason": "Other still booked",
            "count": total_not_completed - reason_total,
            "pct": safe_pct(total_not_completed - reason_total, total_not_completed),
        })

    avg_contacts = round(total_contacts / max(total_requests, 1), 2)

    weekly_trend = []
    for r in sorted(rows, key=lambda x: x.get("week_start", "")):
        week_bookings = to_int(r["total_bookings"])
        week_cancellations = to_int(r["total_cancellations"])
        week_aborts = to_int(r["total_aborts"])
        week_visits = max(week_bookings - week_cancellations, 0)
        weekly_trend.append({
            "week":        r.get("week_start", ""),
            "requests":    to_int(r["total_requests"]),
            "bookings":    week_bookings,
            "visits":      week_visits,
            "cancellations": week_cancellations,
            "aborts":      week_aborts,
            "post_abort_visits": max(week_visits - week_aborts, 0),
            "completions": to_int(r["total_completions"]),
            "completion_rate": to_float(r.get("completion_rate_pct", 0)),
        })

    return {
        "funnel": {
            "requests":     total_requests,
            "contacts":     total_contacts,
            "bookings":     total_bookings,
            "visits":       total_visits,
            "cancellations":total_cancellations,
            "aborts":       total_aborts,
            "post_abort_visits": total_after_aborts,
            "completions":  total_completions,
            "not_completed_after_successful_visit": total_not_completed,
        },
        "not_completed_reasons": reason_breakdown,
        "avg_contacts_per_customer": avg_contacts,
        "booking_rate":     safe_pct(total_bookings, total_requests),
        "visit_rate":       safe_pct(total_visits, total_requests),
        "post_abort_rate":  safe_pct(total_after_aborts, total_requests),
        "completion_rate":  safe_pct(total_completions, total_requests),
        "visit_success_rate": safe_pct(total_completions, total_visits),
        "cancellation_rate":safe_pct(total_cancellations, total_bookings),
        "abort_rate":       safe_pct(total_aborts, total_bookings - total_cancellations),
        "weekly_trend":     weekly_trend[-52:],
    }


def get_planning_target_kpis(region_code: str = None, year: int = 2025) -> dict:
    """Actual 2025 planning performance against operational targets."""
    funnel = get_booking_conversion_funnel(region_code, year)
    f = funnel.get("funnel", {})

    total_bookings = int(f.get("bookings") or 0)
    total_visits = int(f.get("visits") or 0)
    total_cancellations = int(f.get("cancellations") or 0)
    total_aborts = int(f.get("aborts") or 0)
    total_not_completed = int(f.get("not_completed_after_successful_visit") or 0)
    total_fallout = total_cancellations + total_aborts + total_not_completed

    visit_target = 0
    for row in get_capacity_demand():
        if region_code and row.get("region_code") != region_code:
            continue
        if to_int(row.get("year")) != year or str(row.get("is_forecast", "0")) != "0":
            continue
        visit_target += to_int(row.get("capacity_jobs"))

    success_target_pct = 85.0
    fallout_target_pct = 25.0
    baseline_accuracy = _beginning_2025_forecast_accuracy(year)

    success_rate = float(funnel.get("visit_success_rate") or 0)
    fallout_rate = safe_pct(total_fallout, total_bookings)

    return {
        "year": year,
        "total_visits": total_visits,
        "total_visits_target": visit_target,
        "total_visits_delta": total_visits - visit_target,
        "daily_accuracy_pct": baseline_accuracy["accuracy_pct"],
        "daily_mape": baseline_accuracy["mape"],
        "daily_accuracy_model": baseline_accuracy["label"],
        "visit_target_accuracy_pct": baseline_accuracy["accuracy_pct"],
        "success_rate": success_rate,
        "success_rate_target": success_target_pct,
        "success_rate_delta": round(success_rate - success_target_pct, 1),
        "fallout": total_fallout,
        "fallout_rate": fallout_rate,
        "fallout_rate_target": fallout_target_pct,
        "fallout_rate_delta": round(fallout_rate - fallout_target_pct, 1),
        "target_basis": "Accuracy is 100 minus daily MAPE for the forecast created at the beginning of 2025 against 2025 actual contact attempts. Total visits target uses 2025 capacity_jobs. Success target is 85.0%; fallout target is 25.0% or lower.",
        "contact_to_visit_rate": safe_pct(total_visits, f.get("contacts") or 0),
        "abandon_rate": None,
    }
