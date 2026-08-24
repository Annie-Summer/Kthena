#!/usr/bin/env python3
"""AASP metrics adapter: poll infer-recommendations API and expose Prometheus gauges."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOG = logging.getLogger("aasp-metrics-adapter")

BASE_URL = os.environ.get("BASE_URL", "https://apigw-beta.huawei.com").rstrip("/")
PROJECT_ID = os.environ.get("PROJECT_ID", "")
SERVICE_GROUP_ID = os.environ.get("SERVICE_GROUP_ID", "")
REGION = os.environ.get("REGION", "")
TOKEN = os.environ.get("TOKEN", "")
WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "5"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "15"))
METRICS_PORT = int(os.environ.get("METRICS_PORT", "8000"))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "10"))
# MOCK=1: do not call API; serve values from MOCK_* env (for offline /scale demo).
MOCK = os.environ.get("MOCK", "0") == "1"
MOCK_RPM = float(os.environ.get("MOCK_RPM", "100"))
MOCK_PROMPT_TPM = float(os.environ.get("MOCK_PROMPT_TPM", "32"))
MOCK_COMPLETION_TPM = float(os.environ.get("MOCK_COMPLETION_TPM", "32"))

state_lock = threading.Lock()
state: dict[str, Any] = {
    "rpm": 0.0,
    "prompt_tpm": 0.0,
    "completion_tpm": 0.0,
    "total_tpm": 0.0,
    "latency": 0.0,
    "last_error": "",
    "last_success": "",
    "adapter_up": 0,
}


def fmt_time(dt: datetime) -> str:
    """Format time like the API example: 2026-03-30T08:00:00."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_url(now: datetime | None = None) -> str:
    if not PROJECT_ID or not SERVICE_GROUP_ID:
        raise ValueError("PROJECT_ID and SERVICE_GROUP_ID are required")
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    start = fmt_time(now)
    end = fmt_time(now + timedelta(minutes=WINDOW_MINUTES))
    # Keep timestamps unescaped to match API docs (…T08:00:00).
    query = f"start_time={start}&end_time={end}"
    if REGION:
        query += f"&region={REGION}"
    return (
        f"{BASE_URL}/v1/{PROJECT_ID}/{SERVICE_GROUP_ID}/infer-recommendations"
        f"?{query}"
    )


def pick_resources(body: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize resources which may be an object or a list."""
    res = body.get("resources")
    if res is None:
        return None
    if isinstance(res, list):
        if not res:
            return None
        if REGION:
            for item in res:
                if isinstance(item, dict) and item.get("region") == REGION:
                    return item
        first = res[0]
        return first if isinstance(first, dict) else None
    if isinstance(res, dict):
        return res
    return None


def max_from_predictions(predictions: list[Any], key: str) -> float:
    values: list[float] = []
    for item in predictions:
        if not isinstance(item, dict):
            continue
        raw = item.get(key)
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
    return max(values) if values else 0.0


def apply_peaks(
    rpm: float,
    prompt_tpm: float,
    completion_tpm: float,
    total_tpm: float = 0.0,
    latency: float = 0.0,
    error: str = "",
) -> None:
    with state_lock:
        if error:
            # Keep last good values on failure; only refresh error / up flag.
            state["last_error"] = error
            state["adapter_up"] = 0
            return
        state["rpm"] = rpm
        state["prompt_tpm"] = prompt_tpm
        state["completion_tpm"] = completion_tpm
        state["total_tpm"] = total_tpm
        state["latency"] = latency
        state["last_error"] = ""
        state["last_success"] = datetime.now(timezone.utc).isoformat()
        state["adapter_up"] = 1


def fetch_once() -> None:
    if MOCK:
        apply_peaks(MOCK_RPM, MOCK_PROMPT_TPM, MOCK_COMPLETION_TPM, MOCK_PROMPT_TPM + MOCK_COMPLETION_TPM)
        LOG.info(
            "mock peaks rpm=%s prompt_tpm=%s completion_tpm=%s",
            MOCK_RPM,
            MOCK_PROMPT_TPM,
            MOCK_COMPLETION_TPM,
        )
        return

    if not TOKEN:
        apply_peaks(0, 0, 0, error="TOKEN is empty")
        return

    try:
        url = build_url()
    except ValueError as exc:
        apply_peaks(0, 0, 0, error=str(exc))
        return

    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        apply_peaks(0, 0, 0, error=f"HTTP {exc.code}: {detail}")
        LOG.warning("fetch failed: HTTP %s %s", exc.code, detail)
        return
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        apply_peaks(0, 0, 0, error=str(exc))
        LOG.warning("fetch failed: %s", exc)
        return

    if isinstance(body, dict) and body.get("error_code"):
        apply_peaks(
            0,
            0,
            0,
            error=f"{body.get('error_code')}: {body.get('error_msg')}",
        )
        return

    resources = pick_resources(body if isinstance(body, dict) else {})
    predictions = (resources or {}).get("predictions") or []
    if not isinstance(predictions, list) or not predictions:
        apply_peaks(0, 0, 0, error="empty predictions")
        return

    rpm = max_from_predictions(predictions, "rpm")
    prompt = max_from_predictions(predictions, "prompt_tpm")
    completion = max_from_predictions(predictions, "completion_tpm")
    total = max_from_predictions(predictions, "total_tpm")
    latency = max_from_predictions(predictions, "latency")
    apply_peaks(rpm, prompt, completion, total, latency)
    LOG.info(
        "updated peaks rpm=%s prompt_tpm=%s completion_tpm=%s points=%d",
        rpm,
        prompt,
        completion,
        len(predictions),
    )


def render_metrics() -> bytes:
    with state_lock:
        snap = dict(state)

    labels = (
        f'service_group_id="{SERVICE_GROUP_ID}",'
        f'region="{REGION}"'
    )
    lines = [
        "# HELP aasp_predicted_rpm max rpm over AASP prediction window",
        "# TYPE aasp_predicted_rpm gauge",
        f"aasp_predicted_rpm{{{labels}}} {snap['rpm']}",
        "# HELP aasp_predicted_prompt_tpm max prompt_tpm over AASP prediction window",
        "# TYPE aasp_predicted_prompt_tpm gauge",
        f"aasp_predicted_prompt_tpm{{{labels}}} {snap['prompt_tpm']}",
        "# HELP aasp_predicted_completion_tpm max completion_tpm over AASP prediction window",
        "# TYPE aasp_predicted_completion_tpm gauge",
        f"aasp_predicted_completion_tpm{{{labels}}} {snap['completion_tpm']}",
        "# HELP aasp_predicted_total_tpm max total_tpm over AASP prediction window",
        "# TYPE aasp_predicted_total_tpm gauge",
        f"aasp_predicted_total_tpm{{{labels}}} {snap['total_tpm']}",
        "# HELP aasp_predicted_latency_ms max latency over AASP prediction window",
        "# TYPE aasp_predicted_latency_ms gauge",
        f"aasp_predicted_latency_ms{{{labels}}} {snap['latency']}",
        "# HELP aasp_adapter_up 1 if last AASP fetch succeeded",
        "# TYPE aasp_adapter_up gauge",
        f"aasp_adapter_up{{{labels}}} {snap['adapter_up']}",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.debug("http: " + fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        payload = render_metrics()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def poll_loop() -> None:
    while True:
        try:
            fetch_once()
        except Exception:
            LOG.exception("unexpected error in poll loop")
            apply_peaks(0, 0, 0, error="unexpected poll error")
        time.sleep(POLL_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOG.info(
        "starting adapter mock=%s port=%s poll=%ss window=%sm base=%s",
        MOCK,
        METRICS_PORT,
        POLL_SECONDS,
        WINDOW_MINUTES,
        BASE_URL,
    )
    # Prime metrics once before serving.
    fetch_once()
    threading.Thread(target=poll_loop, name="aasp-poller", daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", METRICS_PORT), MetricsHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
