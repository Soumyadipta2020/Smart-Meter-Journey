"""
IMSERV Smart Meter Appointment Planning & Utility Operations Platform
Flask application — extends DAA-Project architecture patterns.

Modules:
  1. Appointment Journey              — executive funnel dashboard
  2. Contact Centre Forecasting       — multi-model channel forecasting
  3. Appointment Fallout             — root cause + AI prediction
  4. Field Operations & Engineer Planning — scheduling + optimisation
  5. Financial Scenario Planning      — cost/revenue simulation
"""
import os
import json
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from dotenv import load_dotenv

# ─── Environment ─────────────────────────────────────────────────────────────
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# ─── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "imserv-dev-secret-2026")
CORS(app)
_DATA_READY = False
SUPPORTED_YEARS = {2025, 2026}

def _request_year(default: int = 2025) -> int:
    """Return a supported dashboard year; stale years fall back to 2025."""
    try:
        year = int(request.args.get("year", default))
    except (TypeError, ValueError):
        return default
    return year if year in SUPPORTED_YEARS else default

# ─── After-request: no-cache for all /api/* routes (mirrors DAA pattern) ─────
@app.after_request
def add_api_no_cache_headers(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
    return response


# ─── Lazy Engine Imports (avoids startup cost if data not yet generated) ─────
def _get_forecasting_engine():
    from engine.forecasting_engine import (
        forecast_channel_volume, get_channel_kpis, get_booking_conversion_funnel
    )
    return forecast_channel_volume, get_channel_kpis, get_booking_conversion_funnel

def _get_cancellation_engine():
    from engine.cancellation_engine import (
        get_cancellation_kpis, get_cancellation_root_causes,
        get_cancellation_trends, get_regional_cancellation_heatmap,
        predict_cancellation_risk, get_rebooking_analytics
    )
    return (get_cancellation_kpis, get_cancellation_root_causes,
            get_cancellation_trends, get_regional_cancellation_heatmap,
            predict_cancellation_risk, get_rebooking_analytics)

def _get_field_ops_engine():
    from engine.field_ops_engine import (
        get_field_ops_kpis, get_region_capacity_matrix, get_patch_level_plan,
        get_engineer_performance, predict_understaffing, optimise_workforce_allocation,
        get_capacity_forecast_2026
    )
    return (get_field_ops_kpis, get_region_capacity_matrix, get_patch_level_plan,
            get_engineer_performance, predict_understaffing, optimise_workforce_allocation,
            get_capacity_forecast_2026)

def _get_financial_engine():
    from engine.financial_engine import (
        get_financial_kpis, run_scenario, compare_scenarios, get_forecast_profitability
    )
    return get_financial_kpis, run_scenario, compare_scenarios, get_forecast_profitability

def _get_ai_engine():
    from engine.ai_recommendations import get_all_recommendations, get_natural_language_summary
    return get_all_recommendations, get_natural_language_summary

def _ai_enabled() -> bool:
    return os.getenv("ENABLE_AI_RECOMMENDATIONS", "true").lower() == "true"

def _disabled_ai_payload(max_results: int = 20) -> dict:
    return {
        "recommendations": [],
        "total_count": 0,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "action_required_count": 0,
        "disabled": True,
        "message": "AI recommendations are disabled on this deployment.",
    }

def _compact_chat_messages(messages: list[dict], limit: int = 10) -> list[dict]:
    """Keep a small, safe conversation window for the LLM request."""
    compact = []
    for msg in (messages or [])[-limit:]:
        role = msg.get("role") if isinstance(msg, dict) else ""
        content = msg.get("content") if isinstance(msg, dict) else ""
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            compact.append({"role": role, "content": content[:1800]})
    return compact

def _chatbot_context(region: str | None, year: int, view: str | None) -> str:
    """Build a compact app snapshot so the chatbot can answer app-specific questions."""
    lines = [
        "IMSERV Smart Meter Appointment Planning & Utility Operations Platform.",
        "Modules: Appointment Journey, Contact Attempt Forecast, Risk & Recovery, Resource Planning, Scenario Impact.",
        f"Current view: {view or 'unknown'}. Region filter: {region or 'All Regions'}. Year: {year}.",
    ]

    try:
        get_journey, _, to_int_fn, _, safe_pct_fn, _ = _get_ingestion()
        rows = [
            r for r in get_journey()
            if (not region or r.get("region_code") == region)
            and to_int_fn(r.get("year")) == year
            and r.get("is_forecast", "0") == "0"
        ]
        requests_total = sum(to_int_fn(r.get("total_requests")) for r in rows)
        bookings_total = sum(to_int_fn(r.get("total_bookings")) for r in rows)
        cancellations_total = sum(to_int_fn(r.get("total_cancellations")) for r in rows)
        aborts_total = sum(to_int_fn(r.get("total_aborts")) for r in rows)
        completions_total = sum(to_int_fn(r.get("total_completions")) for r in rows)
        visits_total = max(bookings_total - cancellations_total, 0)
        lines.append(
            "Appointment journey snapshot: "
            f"{requests_total:,} appointments booked, {visits_total:,} total visits, "
            f"{cancellations_total:,} D-1 cancellations, {aborts_total:,} same-day aborts, "
            f"{completions_total:,} executed successfully, "
            f"{safe_pct_fn(completions_total, requests_total):.1f}% success rate."
        )
    except Exception as exc:
        lines.append(f"Appointment journey snapshot unavailable: {exc}")

    try:
        get_kpis, _, _, get_forecast = _get_financial_engine()
        financial = get_kpis(region, 2026)
        forecast = get_forecast(region)
        margin = financial.get("gross_margin_pct")
        revenue = financial.get("total_revenue")
        cost = financial.get("total_cost")
        if revenue is not None and cost is not None:
            lines.append(
                "Financial snapshot: "
                f"GBP {float(revenue):,.0f} revenue, GBP {float(cost):,.0f} cost"
                + (f", {float(margin):.1f}% gross margin." if margin is not None else ".")
            )
        if forecast and isinstance(forecast, dict):
            lines.append("Scenario planning uses appointments booked, success rate, D-1 cancellation rate, same-day abort rate, revenue uplift, cost change, and engineer count.")
    except Exception as exc:
        lines.append(f"Financial snapshot unavailable: {exc}")

    try:
        get_kpis, _, _, _, _, _, _ = _get_field_ops_engine()
        ops = get_kpis(region, 2026)
        if ops:
            engineers = ops.get("total_engineers") or ops.get("engineers")
            utilisation = ops.get("avg_utilisation") or ops.get("avg_utilisation_pct")
            completed = ops.get("jobs_completed") or ops.get("total_jobs_completed")
            lines.append(
                "Resource snapshot: "
                f"{engineers if engineers is not None else 'unknown'} engineers, "
                f"{completed if completed is not None else 'unknown'} executed appointments, "
                f"{utilisation if utilisation is not None else 'unknown'} average utilisation."
            )
    except Exception as exc:
        lines.append(f"Resource snapshot unavailable: {exc}")

    try:
        if _ai_enabled():
            get_recs, get_summary = _get_ai_engine()
            recs = get_recs(year, 5)
            summary = get_summary(year, recs)
            lines.append(f"Operational AI summary: {summary}")
    except Exception:
        pass

    return "\n".join(lines)[:5000]

def _huggingface_chat(messages: list[dict]) -> str:
    token = (
        os.getenv("HF_TOKEN")
        or os.getenv("HF_API_KEY")
        or os.getenv("HUGGINGFACE_API_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    )
    if not token:
        raise RuntimeError("Missing HF_TOKEN, HF_API_KEY, or HUGGINGFACE_API_TOKEN on the Flask server.")

    base_url = os.getenv("HF_CHAT_BASE_URL") or os.getenv("HUGGINGFACE_CHAT_BASE_URL") or "https://router.huggingface.co/v1"
    endpoint = os.getenv("HF_CHAT_ENDPOINT") or os.getenv("HUGGINGFACE_CHAT_ENDPOINT") or f"{base_url.rstrip('/')}/chat/completions"
    provider = os.getenv("HF_CHAT_PROVIDER") or os.getenv("HUGGINGFACE_CHAT_PROVIDER")
    if not provider and token.startswith("sk_"):
        provider = "novita"
    model = os.getenv("HF_CHAT_MODEL") or os.getenv("HUGGINGFACE_CHAT_MODEL") or "google/gemma-4-31B-it"
    timeout = float(os.getenv("HF_CHAT_TIMEOUT_SECONDS", "45"))
    max_tokens = int(os.getenv("HF_CHAT_MAX_TOKENS", "450"))
    temperature = float(os.getenv("HF_CHAT_TEMPERATURE", "0.35"))

    if provider:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("Install huggingface_hub from requirements.txt to use HF_CHAT_PROVIDER.") from exc

        client = InferenceClient(
            provider=provider,
            api_key=token,
            timeout=timeout,
        )
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            detail = str(exc)
            if "401" in detail or "Unauthorized" in detail:
                raise RuntimeError(
                    "Hugging Face/Novita rejected the API key. Check that HF_TOKEN contains the full active key, "
                    "that HF_CHAT_PROVIDER matches the key provider, and restart Flask after editing .env."
                ) from exc
            raise RuntimeError(f"Hugging Face provider request failed: {exc}") from exc
        content = completion.choices[0].message.content if completion.choices else None
        if content:
            return str(content).strip()
        raise RuntimeError("Hugging Face provider response did not include assistant content.")

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Hugging Face endpoint returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Hugging Face endpoint: {exc.reason}") from exc

    data = json.loads(raw)
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content") or choices[0].get("text")
        if content:
            return content.strip()
    if data.get("generated_text"):
        return str(data["generated_text"]).strip()
    raise RuntimeError("Hugging Face response did not include assistant content.")

def _get_ingestion():
    from engine.ingestion import get_booking_journey, data_health, to_int, to_float, safe_pct, iter_jobs
    return get_booking_journey, data_health, to_int, to_float, safe_pct, iter_jobs


# ─────────────────────────────────────────────────────────────────────────────
# FRONTEND VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 1 — BOOKINGS TO COMPLETIONS JOURNEY
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/journey/kpis")
def journey_kpis():
    """Top-level funnel KPIs for the executive dashboard."""
    region = request.args.get("region")
    year   = _request_year()
    try:
        get_journey, _, to_int_fn, to_float_fn, safe_pct_fn, iter_jobs_fn = _get_ingestion()
        rows = get_journey()
        if region:
            rows = [r for r in rows if r["region_code"] == region]
        rows = [r for r in rows if to_int_fn(r.get("year")) == year and r.get("is_forecast", "0") == "0"]

        total_requests      = sum(to_int_fn(r["total_requests"])      for r in rows)
        total_contacts      = sum(to_int_fn(r["total_contacts"])       for r in rows)
        total_bookings      = sum(to_int_fn(r["total_bookings"])       for r in rows)
        total_cancellations = sum(to_int_fn(r["total_cancellations"])  for r in rows)
        total_aborts        = sum(to_int_fn(r["total_aborts"])         for r in rows)
        total_completions   = sum(to_int_fn(r["total_completions"])    for r in rows)
        total_visits        = max(total_bookings - total_cancellations, 0)
        total_after_aborts  = max(total_visits - total_aborts, 0)
        total_not_completed = max(total_after_aborts - total_completions, 0)
        avg_contacts        = round(total_contacts / max(total_requests, 1), 2)
        completion_rate     = safe_pct_fn(total_completions, total_requests)
        reason_labels = {
            "EXCHANGE": "Exchange still booked",
            "NEW_INSTALL": "Install still booked",
            "REPAIR": "Repair follow-up booked",
            "REMOVAL": "Removal still booked",
        }
        not_completed_reasons = Counter()
        for job in iter_jobs_fn():
            if region and job.get("region_code") != region:
                continue
            if job.get("requested_date", "")[:4] != str(year) or job.get("is_forecast", "0") != "0":
                continue
            if job.get("status") == "Booked":
                not_completed_reasons[job.get("job_type") or "Other"] += 1

        reason_breakdown = [
            {
                "reason": reason_labels.get(reason, reason.replace("_", " ").title()),
                "count": count,
                "pct": safe_pct_fn(count, total_not_completed),
            }
            for reason, count in not_completed_reasons.most_common()
        ]
        reason_total = sum(item["count"] for item in reason_breakdown)
        if total_not_completed > reason_total:
            reason_breakdown.append({
                "reason": "Other still booked",
                "count": total_not_completed - reason_total,
                "pct": safe_pct_fn(total_not_completed - reason_total, total_not_completed),
            })

        return jsonify({
            "unique_customers":       total_requests,
            "total_requests":        total_requests,
            "total_contacts":        total_contacts,
            "avg_contacts_per_customer": avg_contacts,
            "total_bookings":        total_bookings,
            "total_visits":          total_visits,
            "total_cancellations":   total_cancellations,
            "total_aborts":          total_aborts,
            "total_post_abort_visits": total_after_aborts,
            "total_not_completed_after_successful_visit": total_not_completed,
            "total_completions":     total_completions,
            "not_completed_reasons": reason_breakdown,
            "completion_rate":       completion_rate,
            "booking_rate":          safe_pct_fn(total_bookings, total_requests),
            "visit_rate":            safe_pct_fn(total_visits, total_requests),
            "post_abort_rate":       safe_pct_fn(total_after_aborts, total_requests),
            "visit_success_rate":    safe_pct_fn(total_completions, total_visits),
            "cancellation_rate":     safe_pct_fn(total_cancellations, total_bookings),
            "abort_rate":            safe_pct_fn(total_aborts, total_bookings - total_cancellations),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/journey/weekly-trend")
def journey_weekly_trend():
    """Weekly completion rate trend for line chart."""
    region = request.args.get("region")
    year   = _request_year()
    try:
        get_journey, _, to_int_fn, to_float_fn, _, _ = _get_ingestion()
        rows = get_journey()
        if region:
            rows = [r for r in rows if r["region_code"] == region]
        rows = [r for r in rows if to_int_fn(r.get("year")) == year and r.get("is_forecast", "0") == "0"]
        rows = sorted(rows, key=lambda x: x.get("week_start", ""))

        weekly = {}
        for r in rows:
            wk = r.get("week_start", "")[:10]
            if wk not in weekly:
                weekly[wk] = {"requests": 0, "bookings": 0, "visits": 0, "completions": 0, "cancellations": 0, "aborts": 0}
            bookings = to_int_fn(r["total_bookings"])
            cancellations = to_int_fn(r["total_cancellations"])
            weekly[wk]["requests"]     += to_int_fn(r["total_requests"])
            weekly[wk]["bookings"]     += bookings
            weekly[wk]["visits"]       += max(bookings - cancellations, 0)
            weekly[wk]["completions"]  += to_int_fn(r["total_completions"])
            weekly[wk]["cancellations"]+= cancellations
            weekly[wk]["aborts"]       += to_int_fn(r["total_aborts"])

        labels, requests, bookings, visits, completions, cancellations, aborts = [], [], [], [], [], [], []
        for wk in sorted(weekly.keys()):
            d = weekly[wk]
            labels.append(wk)
            requests.append(d["requests"])
            bookings.append(d["bookings"])
            visits.append(d["visits"])
            completions.append(d["completions"])
            cancellations.append(d["cancellations"])
            aborts.append(d["aborts"])

        return jsonify({
            "labels":        labels,
            "requests":      requests,
            "bookings":      bookings,
            "visits":        visits,
            "completions":   completions,
            "cancellations": cancellations,
            "aborts":        aborts,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/journey/suppliers")
def journey_suppliers():
    """Supplier-level contribution and behaviour analytics for the journey tab."""
    region = request.args.get("region")
    year = _request_year()
    top_n = int(request.args.get("top_n", 18))
    try:
        _, _, to_int_fn, _, safe_pct_fn, iter_jobs_fn = _get_ingestion()
        by_supplier = {}
        totals = {
            "requests": 0,
            "contacts": 0,
            "bookings": 0,
            "visits": 0,
            "completions": 0,
            "cancellations": 0,
            "aborts": 0,
            "unbooked": 0,
            "unresolved": 0,
        }

        for job in iter_jobs_fn():
            if region and job.get("region_code") != region:
                continue
            if job.get("requested_date", "")[:4] != str(year) or job.get("is_forecast", "0") != "0":
                continue

            supplier = (job.get("supplier_name") or "Unassigned Supplier").strip()
            bucket = by_supplier.setdefault(supplier, {
                "supplier_name": supplier,
                "requests": 0,
                "contacts": 0,
                "bookings": 0,
                "visits": 0,
                "completions": 0,
                "cancellations": 0,
                "aborts": 0,
                "unbooked": 0,
                "unresolved": 0,
                "channels": Counter(),
                "job_types": Counter(),
            })

            status = job.get("status")
            booked = bool(job.get("booked_date"))
            cancelled = status == "Cancelled"
            aborted = status == "Aborted"
            completed = status == "Completed"
            unresolved = status == "Booked"
            unbooked = not booked and status == "Unbooked"
            visits = 1 if booked and not cancelled else 0
            contacts = to_int_fn(job.get("contacts_count"))

            bucket["requests"] += 1
            bucket["contacts"] += contacts
            bucket["bookings"] += 1 if booked else 0
            bucket["visits"] += visits
            bucket["completions"] += 1 if completed else 0
            bucket["cancellations"] += 1 if cancelled else 0
            bucket["aborts"] += 1 if aborted else 0
            bucket["unbooked"] += 1 if unbooked else 0
            bucket["unresolved"] += 1 if unresolved else 0
            bucket["channels"][job.get("primary_channel") or "Unknown"] += 1
            bucket["job_types"][job.get("job_type") or "Other"] += 1

            totals["requests"] += 1
            totals["contacts"] += contacts
            totals["bookings"] += 1 if booked else 0
            totals["visits"] += visits
            totals["completions"] += 1 if completed else 0
            totals["cancellations"] += 1 if cancelled else 0
            totals["aborts"] += 1 if aborted else 0
            totals["unbooked"] += 1 if unbooked else 0
            totals["unresolved"] += 1 if unresolved else 0

        suppliers = []
        for item in by_supplier.values():
            fallout = item["cancellations"] + item["aborts"] + item["unresolved"]
            booking_rate = safe_pct_fn(item["bookings"], item["requests"])
            visit_success_rate = safe_pct_fn(item["completions"], item["visits"])
            fallout_rate = safe_pct_fn(fallout, item["bookings"])
            contribution_pct = round(item["requests"] / max(totals["requests"], 1) * 100, 2)
            behaviour_score = round(
                (booking_rate * 0.25) + (visit_success_rate * 0.55) - (fallout_rate * 0.20),
                1,
            )

            suppliers.append({
                "supplier_name": item["supplier_name"],
                "requests": item["requests"],
                "contacts": item["contacts"],
                "bookings": item["bookings"],
                "visits": item["visits"],
                "completions": item["completions"],
                "cancellations": item["cancellations"],
                "aborts": item["aborts"],
                "unbooked": item["unbooked"],
                "unresolved": item["unresolved"],
                "contribution_pct": contribution_pct,
                "booking_rate": booking_rate,
                "visit_success_rate": visit_success_rate,
                "fallout_rate": fallout_rate,
                "behaviour_score": behaviour_score,
                "dominant_channel": item["channels"].most_common(1)[0][0] if item["channels"] else "Unknown",
                "dominant_job_type": item["job_types"].most_common(1)[0][0] if item["job_types"] else "Other",
                "segment": "",
            })

        if suppliers:
            avg_score = sum(s["behaviour_score"] for s in suppliers) / len(suppliers)
            sorted_requests = sorted(s["requests"] for s in suppliers)
            median_requests = sorted_requests[len(sorted_requests) // 2]
            for supplier in suppliers:
                high_contribution = supplier["requests"] >= median_requests
                strong_behaviour = supplier["behaviour_score"] >= avg_score
                if high_contribution and strong_behaviour:
                    supplier["segment"] = "Scale and stable"
                elif high_contribution:
                    supplier["segment"] = "High-volume watch"
                elif strong_behaviour:
                    supplier["segment"] = "Efficient niche"
                else:
                    supplier["segment"] = "Needs attention"

        suppliers.sort(key=lambda r: (r["requests"], r["behaviour_score"]), reverse=True)
        leaders = sorted(suppliers, key=lambda r: r["visit_success_rate"], reverse=True)[:5]
        watchlist = sorted(suppliers, key=lambda r: (r["fallout_rate"], r["requests"]), reverse=True)[:5]
        total_fallout = totals["cancellations"] + totals["aborts"] + totals["unresolved"]

        return jsonify({
            "suppliers": suppliers[:max(top_n, 1)],
            "leaderboard": leaders,
            "watchlist": watchlist,
            "totals": {
                **totals,
                "fallout": total_fallout,
                "booking_rate": safe_pct_fn(totals["bookings"], totals["requests"]),
                "visit_success_rate": safe_pct_fn(totals["completions"], totals["visits"]),
                "fallout_rate": safe_pct_fn(total_fallout, totals["bookings"]),
            },
            "supplier_count": len(suppliers),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/journey/regional-heatmap")
def journey_regional_heatmap():
    """Regional completion rate heatmap data."""
    year = _request_year()
    try:
        get_journey, _, to_int_fn, to_float_fn, safe_pct_fn, _ = _get_ingestion()
        rows = get_journey()
        rows = [r for r in rows if to_int_fn(r.get("year")) == year and r.get("is_forecast", "0") == "0"]

        by_region = {}
        for r in rows:
            rc = r["region_code"]
            if rc not in by_region:
                by_region[rc] = {"requests": 0, "completions": 0, "cancellations": 0, "aborts": 0, "region_name": r.get("region_name", rc)}
            by_region[rc]["requests"]     += to_int_fn(r["total_requests"])
            by_region[rc]["completions"]  += to_int_fn(r["total_completions"])
            by_region[rc]["cancellations"]+= to_int_fn(r["total_cancellations"])
            by_region[rc]["aborts"]       += to_int_fn(r["total_aborts"])

        result = []
        for rc, d in by_region.items():
            cr = safe_pct_fn(d["completions"], d["requests"])
            rag = "Green" if cr >= 65 else ("Amber" if cr >= 55 else "Red")
            result.append({
                "region_code":    rc,
                "region_name":    d["region_name"],
                "requests":       d["requests"],
                "completions":    d["completions"],
                "cancellations":  d["cancellations"],
                "aborts":         d["aborts"],
                "completion_rate":cr,
                "rag":            rag,
            })
        result.sort(key=lambda x: -x["completion_rate"])
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/journey/interactions")
def journey_interactions():
    """Customer interaction source/type mapping for journey analytics."""
    region = request.args.get("region")
    year   = _request_year()
    try:
        from engine.forecasting_engine import get_customer_interaction_map
        return jsonify(get_customer_interaction_map(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 2 — CONTACT CENTRE FORECASTING
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/forecasting/channel-kpis")
def forecasting_channel_kpis():
    region = request.args.get("region")
    year   = _request_year()
    try:
        _, get_kpis, _ = _get_forecasting_engine()
        return jsonify(get_kpis(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/forecasting/forecast")
def forecasting_forecast():
    region  = request.args.get("region")
    channel = request.args.get("channel")
    weeks   = int(request.args.get("weeks", 26))
    models  = request.args.getlist("models") or None
    try:
        forecast_fn, _, _ = _get_forecasting_engine()
        return jsonify(forecast_fn(region, channel, weeks, models))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/forecasting/funnel")
def forecasting_funnel():
    region = request.args.get("region")
    year   = _request_year()
    try:
        _, _, get_funnel = _get_forecasting_engine()
        return jsonify(get_funnel(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/forecasting/planning-target-kpis")
def forecasting_planning_target_kpis():
    region = request.args.get("region")
    year = _request_year()
    try:
        from engine.forecasting_engine import get_planning_target_kpis
        return jsonify(get_planning_target_kpis(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# MODULE 3 — APPOINTMENT FALLOUT
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/cancellations/kpis")
def cancellations_kpis():
    region = request.args.get("region")
    year   = _request_year()
    try:
        get_kpis, *_ = _get_cancellation_engine()
        return jsonify(get_kpis(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cancellations/root-causes")
def cancellations_root_causes():
    region        = request.args.get("region")
    year          = _request_year()
    include_aborts= request.args.get("include_aborts", "true").lower() == "true"
    try:
        _, get_rc, *_ = _get_cancellation_engine()
        return jsonify(get_rc(region, year, include_aborts))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cancellations/trends")
def cancellations_trends():
    region = request.args.get("region")
    try:
        _, _, get_trends, *_ = _get_cancellation_engine()
        return jsonify(get_trends(region))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cancellations/heatmap")
def cancellations_heatmap():
    year = _request_year()
    try:
        _, _, _, get_heatmap, *_ = _get_cancellation_engine()
        return jsonify(get_heatmap(year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cancellations/predict")
def cancellations_predict():
    region = request.args.get("region") or None
    try:
        _, _, _, _, predict, _ = _get_cancellation_engine()
        return jsonify(predict(region))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cancellations/rebooking")
def cancellations_rebooking():
    region = request.args.get("region")
    year   = _request_year()
    try:
        *_, get_rebook = _get_cancellation_engine()
        return jsonify(get_rebook(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 4 — FIELD OPERATIONS & ENGINEER PLANNING
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/field-ops/kpis")
def field_ops_kpis():
    region = request.args.get("region")
    year   = _request_year()
    try:
        get_kpis, *_ = _get_field_ops_engine()
        return jsonify(get_kpis(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/field-ops/capacity-matrix")
def field_ops_capacity_matrix():
    year = _request_year()
    try:
        _, get_matrix, *_ = _get_field_ops_engine()
        return jsonify(get_matrix(year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/field-ops/patch-plan")
def field_ops_patch_plan():
    region = request.args.get("region", "NW")
    week   = request.args.get("week")
    year   = _request_year()
    try:
        _, _, get_patch, *_ = _get_field_ops_engine()
        week_int = int(week) if week else None
        return jsonify(get_patch(region, week_int, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/field-ops/engineer-performance")
def field_ops_engineer_performance():
    region = request.args.get("region")
    year   = _request_year()
    top_n  = int(request.args.get("top_n", 20))
    try:
        _, _, _, get_perf, *_ = _get_field_ops_engine()
        return jsonify(get_perf(region, year, top_n))
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/field-ops/capacity-forecast")
def field_ops_capacity_forecast():
    region = request.args.get("region")
    try:
        *_, forecast = _get_field_ops_engine()
        return jsonify(forecast(
            region_code=region,
            target_utilisation_pct=request.args.get("target", 78),
            jobs_per_fte_day=request.args.get("jobs_per_fte_day", 4),
            absence_rate_pct=request.args.get("absence_rate"),
        ))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/field-ops/optimise")
def field_ops_optimise():
    year = _request_year(default=2026)
    try:
        _, _, _, _, _, optimise, *_ = _get_field_ops_engine()
        return jsonify(optimise(
            year=year,
            target_utilisation_pct=request.args.get("target", 72),
            jobs_per_fte_day=request.args.get("jobs_per_fte_day", 4),
            absence_rate_pct=request.args.get("absence_rate", 15),
        ))
    except Exception as e:
        return jsonify({"error": str(e)}), 500




# ─────────────────────────────────────────────────────────────────────────────
# MODULE 5 — FINANCIAL SCENARIO PLANNING
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/financial/kpis")
def financial_kpis():
    region = request.args.get("region")
    year   = _request_year()
    try:
        get_kpis, *_ = _get_financial_engine()
        return jsonify(get_kpis(region, year))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/financial/scenario", methods=["POST"])
def financial_scenario():
    """Run a named financial scenario. Accepts JSON body with scenario parameters."""
    try:
        payload = request.get_json(force=True) or {}
        _, run_sc, _, _ = _get_financial_engine()
        result = run_sc(
            scenario_name          = payload.get("scenario_name", "Custom Scenario"),
            job_volume             = int(payload.get("job_volume", 50000)),
            completion_rate_pct    = float(payload.get("completion_rate_pct", 68.0)),
            cancel_rate_pct        = float(payload.get("cancel_rate_pct", 15.0)),
            abort_rate_pct         = float(payload.get("abort_rate_pct", 8.0)),
            revenue_uplift_pct     = float(payload.get("revenue_uplift_pct", 0.0)),
            cost_uplift_pct        = float(payload.get("cost_uplift_pct", 0.0)),
            engineer_count         = int(payload.get("engineer_count", 300)),
            productivity_jobs_per_day= float(payload.get("productivity_jobs_per_day", 4.0)),
            region_code            = payload.get("region_code"),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/financial/compare-scenarios", methods=["POST"])
def financial_compare():
    """Compare multiple scenarios. Accepts JSON body: {scenarios: [...]}."""
    try:
        payload   = request.get_json(force=True) or {}
        scenarios = payload.get("scenarios", [])
        if not scenarios:
            return jsonify({"error": "No scenarios provided"}), 400
        _, _, compare, _ = _get_financial_engine()
        return jsonify(compare(scenarios))
    except Exception as e:
        app.logger.exception("Failed to compare financial scenarios")
        return jsonify({"error": "An internal error has occurred."}), 500


@app.route("/api/financial/forecast-profitability")
def financial_forecast():
    region = request.args.get("region")
    try:
        _, _, _, get_forecast = _get_financial_engine()
        return jsonify(get_forecast(region))
    except Exception as e:
        app.logger.exception("Failed to forecast financial profitability")
        return jsonify({"error": "An internal error has occurred."}), 500


# ─────────────────────────────────────────────────────────────────────────────
# AI RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/ai/recommendations")
def ai_recommendations():
    year        = _request_year()
    max_results = int(request.args.get("max", 20))
    try:
        if not _ai_enabled():
            return jsonify(_disabled_ai_payload(max_results))
        get_recs, _ = _get_ai_engine()
        return jsonify(get_recs(year, max_results))
    except Exception as e:
        app.logger.exception("Failed to generate AI recommendations")
        return jsonify({"error": "An internal error has occurred."}), 500


@app.route("/api/ai/summary")
def ai_summary():
    year = _request_year()
    try:
        if not _ai_enabled():
            return jsonify({"summary": "AI recommendations are disabled on this deployment."})
        _, get_summary = _get_ai_engine()
        return jsonify({"summary": get_summary(year)})
    except Exception as e:
        app.logger.exception("Failed to generate AI summary")
        return jsonify({"error": "An internal error has occurred."}), 500


@app.route("/api/ai/dashboard")
def ai_dashboard():
    year        = _request_year()
    max_results = int(request.args.get("max", 20))
    try:
        if not _ai_enabled():
            recs = _disabled_ai_payload(max_results)
            return jsonify({
                "recommendations": recs,
                "summary": recs["message"],
            })
        get_recs, get_summary = _get_ai_engine()
        recs = get_recs(year, max_results)
        return jsonify({
            "recommendations": recs,
            "summary": get_summary(year, recs),
        })
    except Exception as e:
        app.logger.exception("Failed to build AI dashboard payload")
        return jsonify({"error": "An internal error has occurred."}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM / UTILITY
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/chatbot/message", methods=["POST"])
def chatbot_message():
    """Proxy chatbot conversations to a Hugging Face OpenAI-compatible LLM endpoint."""
    try:
        payload = request.get_json(force=True) or {}
        user_messages = _compact_chat_messages(payload.get("messages", []))
        if not user_messages or user_messages[-1]["role"] != "user":
            return jsonify({"error": "Send at least one user message."}), 400

        region = payload.get("region") or request.args.get("region") or None
        view = payload.get("view") or request.args.get("view") or None
        try:
            year = int(payload.get("year") or request.args.get("year") or 2025)
        except (TypeError, ValueError):
            year = 2025
        if year not in SUPPORTED_YEARS:
            year = 2025

        context = _chatbot_context(region, year, view)
        system_prompt = (
            "You are the IMSERV app assistant. Help users understand and use this smart meter "
            "operations dashboard. Be concise, practical, and app-specific. Use the provided "
            "snapshot for numbers. If a user asks for a metric not in the snapshot, say where "
            "in the app they can inspect it instead of inventing values.\n\n"
            f"App snapshot:\n{context}"
        )
        messages = [{"role": "system", "content": system_prompt}] + user_messages
        answer = _huggingface_chat(messages)
        return jsonify({"reply": answer})
    except RuntimeError as exc:
        return jsonify({
            "error": str(exc),
            "config_required": "Set HF_TOKEN or HF_API_KEY, plus HF_CHAT_MODEL. Set HF_CHAT_PROVIDER=novita for provider-based Hugging Face examples.",
        }), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/chatbot/config")
def chatbot_config():
    """Return non-secret chatbot configuration for deployment diagnostics."""
    token = (
        os.getenv("HF_TOKEN")
        or os.getenv("HF_API_KEY")
        or os.getenv("HUGGINGFACE_API_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        or ""
    )
    provider = os.getenv("HF_CHAT_PROVIDER") or os.getenv("HUGGINGFACE_CHAT_PROVIDER")
    inferred_provider = provider or ("novita" if token.startswith("sk_") else "")
    return jsonify({
        "has_token": bool(token),
        "token_prefix": token[:3] if token else "",
        "token_length": len(token),
        "provider": provider or "",
        "effective_provider": inferred_provider,
        "model": os.getenv("HF_CHAT_MODEL") or os.getenv("HUGGINGFACE_CHAT_MODEL") or "google/gemma-4-31B-it",
        "base_url": os.getenv("HF_CHAT_BASE_URL") or os.getenv("HUGGINGFACE_CHAT_BASE_URL") or "https://router.huggingface.co/v1",
        "endpoint_set": bool(os.getenv("HF_CHAT_ENDPOINT") or os.getenv("HUGGINGFACE_CHAT_ENDPOINT")),
    })


@app.route("/api/health")
def health():
    """Health check endpoint for Render.com and Docker."""
    from engine.ingestion import data_health
    dh = data_health()
    all_ok = all(v["exists"] for v in dh.values())
    return jsonify({
        "status":     "ok" if all_ok else "degraded",
        "data_health":dh,
        "timestamp":  datetime.utcnow().isoformat() + "Z",
        "version":    "1.0.0",
    }), 200 if all_ok else 206


@app.route("/api/data/reload")
def data_reload():
    """Clear in-memory data caches so the next request reloads only what it needs."""
    from engine.ingestion import clear_data_caches
    from engine.forecasting_engine import clear_forecast_cache
    health_info = clear_data_caches()
    clear_forecast_cache()
    return jsonify({"status": "ok", "message": "Data caches cleared", "data_health": health_info})


@app.route("/api/data/generate")
def data_generate():
    """Trigger synthetic data generation (dev/reset use only)."""
    try:
        if os.getenv("RENDER") and os.getenv("IMSERV_ENABLE_DATA_GENERATE", "").lower() != "true":
            return jsonify({
                "error": "Dataset generation is disabled on Render to stay within memory limits.",
                "hint": "Set IMSERV_ENABLE_DATA_GENERATE=true only for a one-off maintenance run.",
            }), 403
        from engine.data_generator import generate_all
        from engine.ingestion import clear_data_caches
        from engine.forecasting_engine import clear_forecast_cache
        generate_all()
        health_info = clear_data_caches()
        clear_forecast_cache()
        return jsonify({"status": "ok", "message": "Datasets regenerated successfully", "data_health": health_info})
    except Exception as e:
        app.logger.exception("Data generation failed")
        return jsonify({"error": "An internal error occurred while generating datasets."}), 500


@app.route("/api/regions")
def get_regions():
    return jsonify([
        {"code": "NW",  "name": "North West"},
        {"code": "NE",  "name": "North East"},
        {"code": "MID", "name": "Midlands"},
        {"code": "SE",  "name": "South East"},
        {"code": "SW",  "name": "South West"},
        {"code": "WAL", "name": "Wales"},
        {"code": "SCO", "name": "Scotland"},
        {"code": "YRK", "name": "Yorkshire"},
    ])


# ─── Startup: generate data if missing ───────────────────────────────────────
def _ensure_data():
    """Ensure required data files exist without loading them into memory."""
    global _DATA_READY
    if _DATA_READY:
        return

    manifest = BASE_DIR / "data" / "inputs" / "manifest.json"
    master = BASE_DIR / "data" / "inputs" / "master_operations.csv"
    if not manifest.exists() or not master.exists():
        can_generate = (
            os.getenv("IMSERV_AUTO_GENERATE_DATA", "").lower() == "true"
            or (
                os.getenv("FLASK_ENV", "development") == "development"
                and not os.getenv("RENDER")
            )
        )
        if can_generate:
            print("IMSERV: Connected data source not found - generating synthetic datasets...")
            try:
                from engine.data_generator import generate_all
                generate_all()
            except Exception as e:
                print(f"IMSERV: Data generation failed: {e}")
        else:
            print("IMSERV: Connected data source missing. Skipping auto-generation on constrained runtime.")

    print("IMSERV: Data files verified. CSVs will be loaded lazily per request.")
    _DATA_READY = True


# ─────────────────────────────────────────────────────────────────────────────

_ensure_data()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    print(f"\nIMSERV Platform running on http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
