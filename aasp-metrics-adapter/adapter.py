#!/usr/bin/env python3
"""AASP metrics adapter: poll infer-recommendations API and expose Prometheus gauges.

When LEADER_ELECTION=1 (in-cluster), only the Lease holder polls AASP and exposes
non-zero predicted gauges; followers expose 0 so Kthena can scrape all pods without ×N.
"""

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

from leader_election import LeaseLeaderElection

LOG = logging.getLogger("aasp-metrics-adapter")

BASE_URL = os.environ.get("BASE_URL", "https://apigw-beta.huawei.com").rstrip("/")
PROJECT_ID = os.environ.get("PROJECT_ID", "")
# Path style:
# - INSTANCE_ID set  → /v1/{PROJECT_ID}/instance/{INSTANCE_ID}/infer-recommendations
# - else SERVICE_GROUP_ID → /v1/{PROJECT_ID}/{SERVICE_GROUP_ID}/infer-recommendations
INSTANCE_ID = os.environ.get("INSTANCE_ID", "")
SERVICE_GROUP_ID = os.environ.get("SERVICE_GROUP_ID", "")
REGION = os.environ.get("REGION", "")
TOKEN = os.environ.get("TOKEN", "")
# Auth: "x-auth-token" (X-Auth-Token header) or "bearer" (Authorization: Bearer …)
AUTH_HEADER = os.environ.get("AUTH_HEADER", "bearer").strip().lower()
WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "5"))
# forward: [now, now+WINDOW); backward: [now-WINDOW, now] (matches many lab curl examples)
TIME_RANGE_MODE = os.environ.get("TIME_RANGE_MODE", "forward").strip().lower()
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "15"))
METRICS_PORT = int(os.environ.get("METRICS_PORT", "8000"))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "10"))
# MOCK=1: do not call API; serve values from MOCK_* env (for offline /scale demo).
MOCK = os.environ.get("MOCK", "0") == "1"
MOCK_RPM = float(os.environ.get("MOCK_RPM", "100"))
MOCK_PROMPT_TPM = float(os.environ.get("MOCK_PROMPT_TPM", "32"))
MOCK_COMPLETION_TPM = float(os.environ.get("MOCK_COMPLETION_TPM", "32"))

# Optional IAM password login for automatic token refresh on 401 (manual TOKEN still supported).
# Enable when IAM_AUTH_URL + IAM_USER + IAM_PASSWORD + IAM_DOMAIN + project name/id are set.
IAM_AUTH_URL = os.environ.get(
    "IAM_AUTH_URL", "https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true"
).strip()
IAM_USER = os.environ.get("IAM_USER", "").strip()
IAM_PASSWORD = os.environ.get("IAM_PASSWORD", "")
IAM_DOMAIN = os.environ.get("IAM_DOMAIN", "").strip()
IAM_PROJECT_NAME = os.environ.get("IAM_PROJECT_NAME", "").strip()
IAM_PROJECT_ID = os.environ.get("IAM_PROJECT_ID", "").strip()
IAM_REFRESH_SKEW_SECONDS = int(os.environ.get("IAM_REFRESH_SKEW_SECONDS", "300"))
IAM_HTTP_TIMEOUT = float(os.environ.get("IAM_HTTP_TIMEOUT", "15"))

# Leader election: only the leader polls AASP and exposes non-zero predicted metrics.
LEADER_ELECTION = os.environ.get("LEADER_ELECTION", "0") == "1"
LEASE_NAME = os.environ.get("LEASE_NAME", "aasp-metrics-leader")
LEASE_DURATION_SECONDS = int(os.environ.get("LEASE_DURATION_SECONDS", "15"))
LEASE_RENEW_SECONDS = float(os.environ.get("LEASE_RENEW_SECONDS", "5"))
POD_NAME = os.environ.get("POD_NAME", "")
POD_NAMESPACE = os.environ.get("POD_NAMESPACE", "")

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

# Runtime token (may be refreshed in-process without pod restart).
_token_lock = threading.Lock()
_runtime_token = TOKEN
_token_expires_at: datetime | None = None

# Set in main(); None means "always leader" (LEADER_ELECTION=0).
_election: LeaseLeaderElection | None = None


def is_leader() -> bool:
    if _election is None:
        return True
    return _election.is_leader()


def iam_auto_refresh_enabled() -> bool:
    """True when IAM password credentials are configured for auto re-login."""
    if not (IAM_AUTH_URL and IAM_USER and IAM_PASSWORD and IAM_DOMAIN):
        return False
    return bool(IAM_PROJECT_NAME or IAM_PROJECT_ID)


def get_runtime_token() -> str:
    with _token_lock:
        return _runtime_token


def set_runtime_token(token: str, expires_at: datetime | None = None) -> None:
    global _runtime_token, _token_expires_at
    with _token_lock:
        _runtime_token = token
        _token_expires_at = expires_at


def _parse_expires_at(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_iam_auth_body() -> dict[str, Any]:
    user: dict[str, Any] = {
        "name": IAM_USER,
        "password": IAM_PASSWORD,
        "domain": {"name": IAM_DOMAIN},
    }
    if IAM_PROJECT_ID:
        scope: dict[str, Any] = {"project": {"id": IAM_PROJECT_ID}}
    else:
        scope = {"project": {"name": IAM_PROJECT_NAME}}
    return {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {"user": user},
            },
            "scope": scope,
        }
    }


def fetch_iam_token() -> tuple[str, datetime | None]:
    """POST IAM /v3/auth/tokens; return (token, expires_at_utc_or_none)."""
    if not iam_auto_refresh_enabled():
        raise RuntimeError("IAM auto-refresh is not configured")
    payload = json.dumps(build_iam_auth_body()).encode("utf-8")
    req = Request(
        IAM_AUTH_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=IAM_HTTP_TIMEOUT) as resp:
            token = (
                resp.headers.get("X-Subject-Token")
                or resp.headers.get("x-subject-token")
                or ""
            ).strip()
            body_raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"IAM HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"IAM request failed: {exc}") from exc

    if not token:
        raise RuntimeError("IAM response missing X-Subject-Token header")

    expires_at = None
    if body_raw:
        try:
            body = json.loads(body_raw)
            if isinstance(body, dict):
                tok = body.get("token")
                if isinstance(tok, dict):
                    expires_at = _parse_expires_at(tok.get("expires_at"))
        except json.JSONDecodeError:
            pass
    return token, expires_at


def refresh_runtime_token(*, reason: str) -> bool:
    """Fetch a new IAM token into memory. Returns True on success."""
    if not iam_auto_refresh_enabled():
        return False
    try:
        token, expires_at = fetch_iam_token()
    except Exception as exc:
        LOG.warning("IAM token refresh failed (%s): %s", reason, exc)
        return False
    set_runtime_token(token, expires_at)
    exp = expires_at.isoformat() if expires_at else "unknown"
    LOG.info("IAM token refreshed (%s); expires_at=%s len=%d", reason, exp, len(token))
    return True


def ensure_runtime_token(*, force: bool = False) -> str:
    """
    Return a usable token.
    - Manual mode: env/Secret TOKEN (optionally already set in memory).
    - Auto mode: login if missing, forced, or near expiry.
    """
    token = get_runtime_token()
    if not iam_auto_refresh_enabled():
        return token

    need_refresh = force or not token
    if not need_refresh:
        with _token_lock:
            exp = _token_expires_at
        if exp is not None:
            skew = timedelta(seconds=max(IAM_REFRESH_SKEW_SECONDS, 0))
            if datetime.now(timezone.utc) >= (exp - skew):
                need_refresh = True

    if need_refresh:
        refresh_runtime_token(reason="ensure" if not force else "forced")
        token = get_runtime_token()
    return token


def fmt_time(dt: datetime) -> str:
    """Format time like the API example: 2026-03-30T08:00:00."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_url(now: datetime | None = None) -> str:
    if not PROJECT_ID:
        raise ValueError("PROJECT_ID is required")
    if not INSTANCE_ID and not SERVICE_GROUP_ID:
        raise ValueError("INSTANCE_ID or SERVICE_GROUP_ID is required")
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if TIME_RANGE_MODE in ("backward", "past", "lookback"):
        start = fmt_time(now - timedelta(minutes=WINDOW_MINUTES))
        end = fmt_time(now)
    else:
        start = fmt_time(now)
        end = fmt_time(now + timedelta(minutes=WINDOW_MINUTES))
    # Keep timestamps unescaped to match API docs (…T08:00:00).
    query = f"start_time={start}&end_time={end}"
    if REGION:
        query += f"&region={REGION}"
    if INSTANCE_ID:
        path = f"/v1/{PROJECT_ID}/instance/{INSTANCE_ID}/infer-recommendations"
    else:
        path = f"/v1/{PROJECT_ID}/{SERVICE_GROUP_ID}/infer-recommendations"
    return f"{BASE_URL}{path}?{query}"


def auth_headers(token: str | None = None) -> dict[str, str]:
    value = token if token is not None else get_runtime_token()
    headers = {"Accept": "application/json"}
    if AUTH_HEADER in ("x-auth-token", "x_auth_token", "token"):
        headers["X-Auth-Token"] = value
    else:
        headers["Authorization"] = f"Bearer {value}"
    return headers


def _prediction_list(resource: dict[str, Any]) -> list[Any]:
    """Return prediction points from a resource object (supports singular/plural)."""
    for key in ("predictions", "prediction"):
        raw = resource.get(key)
        if isinstance(raw, list):
            return raw
    return []


def pick_resource_blocks(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize resources into a list of resource dicts.

    Supported shapes:
    - resources: { predictions: [...] }                 (flat object)
    - resources: [ {region, predictions|prediction}, … ]
    - resources: { "<group_id>": { prediction: [...] }, … }  (lab instance API)
    """
    res = body.get("resources")
    if res is None:
        return []
    if isinstance(res, list):
        items = [x for x in res if isinstance(x, dict)]
        if REGION:
            matched = [x for x in items if x.get("region") == REGION]
            if matched:
                return matched
        return items
    if isinstance(res, dict):
        # Flat resource object (has prediction points at this level).
        if "predictions" in res or "prediction" in res:
            return [res]
        # Map of service-group-id → resource object.
        blocks: list[dict[str, Any]] = []
        for value in res.values():
            if not isinstance(value, dict):
                continue
            if REGION and value.get("region") and value.get("region") != REGION:
                continue
            blocks.append(value)
        return blocks
    return []


def pick_resources(body: dict[str, Any]) -> dict[str, Any] | None:
    """Backward-compatible helper: first normalized resource block, if any."""
    blocks = pick_resource_blocks(body)
    return blocks[0] if blocks else None


def collect_predictions(body: dict[str, Any]) -> list[Any]:
    """Flatten prediction points across all resource blocks."""
    out: list[Any] = []
    for block in pick_resource_blocks(body):
        out.extend(_prediction_list(block))
    return out


def max_from_predictions(predictions: list[Any], *keys: str) -> float:
    """Max over prediction points; try several field names (e.g. prompt_tpm / prompt_token)."""
    values: list[float] = []
    for item in predictions:
        if not isinstance(item, dict):
            continue
        raw = None
        for key in keys:
            if key in item and item.get(key) is not None:
                raw = item.get(key)
                break
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


def _http_get_json(url: str, token: str) -> dict[str, Any]:
    req = Request(url, headers=auth_headers(token), method="GET")
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
        body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("AASP response is not a JSON object")
    return body


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

    token = ensure_runtime_token()
    if not token:
        # Auto mode with empty seed: try one login before failing.
        if iam_auto_refresh_enabled() and refresh_runtime_token(reason="empty-token"):
            token = get_runtime_token()
    if not token:
        apply_peaks(0, 0, 0, error="TOKEN is empty")
        LOG.warning(
            "fetch failed: TOKEN is empty (set TOKEN and/or IAM_* for auto-refresh)"
        )
        return

    try:
        url = build_url()
    except ValueError as exc:
        apply_peaks(0, 0, 0, error=str(exc))
        LOG.warning("fetch failed: %s", exc)
        return

    try:
        body = _http_get_json(url, token)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403) and iam_auto_refresh_enabled():
            LOG.warning(
                "AASP HTTP %s; attempting IAM re-login then one retry", exc.code
            )
            if refresh_runtime_token(reason=f"aasp-http-{exc.code}"):
                try:
                    body = _http_get_json(url, get_runtime_token())
                except HTTPError as retry_exc:
                    detail = retry_exc.read().decode("utf-8", errors="replace")
                    apply_peaks(
                        0, 0, 0, error=f"HTTP {retry_exc.code}: {detail}"
                    )
                    LOG.warning(
                        "fetch failed after IAM refresh: HTTP %s %s",
                        retry_exc.code,
                        detail,
                    )
                    return
                except (URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as retry_exc:
                    apply_peaks(0, 0, 0, error=str(retry_exc))
                    LOG.warning("fetch failed after IAM refresh: %s", retry_exc)
                    return
            else:
                apply_peaks(0, 0, 0, error=f"HTTP {exc.code}: {detail}")
                LOG.warning("fetch failed: HTTP %s %s", exc.code, detail)
                return
        else:
            apply_peaks(0, 0, 0, error=f"HTTP {exc.code}: {detail}")
            LOG.warning("fetch failed: HTTP %s %s", exc.code, detail)
            return
    except (URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        apply_peaks(0, 0, 0, error=str(exc))
        LOG.warning("fetch failed: %s", exc)
        return

    if body.get("error_code"):
        err = f"{body.get('error_code')}: {body.get('error_msg')}"
        apply_peaks(0, 0, 0, error=err)
        LOG.warning("fetch failed: %s", err)
        return

    predictions = collect_predictions(body)
    if not predictions:
        apply_peaks(0, 0, 0, error="empty predictions")
        LOG.warning("fetch failed: empty predictions (check resources shape)")
        return

    rpm = max_from_predictions(predictions, "rpm")
    # Lab API uses prompt_token / completion_token; docs/gateway may use *_tpm.
    prompt = max_from_predictions(predictions, "prompt_tpm", "prompt_token")
    completion = max_from_predictions(predictions, "completion_tpm", "completion_token")
    total = max_from_predictions(predictions, "total_tpm", "total_token")
    if total <= 0 and (prompt > 0 or completion > 0):
        total = prompt + completion
    latency = max_from_predictions(predictions, "latency", "latency_ms")
    apply_peaks(rpm, prompt, completion, total, latency)
    LOG.info(
        "updated peaks rpm=%s prompt_tpm=%s completion_tpm=%s points=%d",
        rpm,
        prompt,
        completion,
        len(predictions),
    )


def render_metrics() -> bytes:
    leader = is_leader()
    with state_lock:
        snap = dict(state)

    # Followers expose zeros so Binding can scrape every pod without ×N.
    if leader:
        rpm = snap["rpm"]
        prompt = snap["prompt_tpm"]
        completion = snap["completion_tpm"]
        total = snap["total_tpm"]
        latency = snap["latency"]
        up = snap["adapter_up"]
    else:
        rpm = prompt = completion = total = latency = 0.0
        up = 0

    unit_id = INSTANCE_ID or SERVICE_GROUP_ID
    labels = (
        f'service_group_id="{unit_id}",'
        f'region="{REGION}",'
        f'pod="{POD_NAME}"'
    )
    lines = [
        "# HELP aasp_predicted_rpm max rpm over AASP prediction window (leader only; followers 0)",
        "# TYPE aasp_predicted_rpm gauge",
        f"aasp_predicted_rpm{{{labels}}} {rpm}",
        "# HELP aasp_predicted_prompt_tpm max prompt_tpm over AASP prediction window (leader only; followers 0)",
        "# TYPE aasp_predicted_prompt_tpm gauge",
        f"aasp_predicted_prompt_tpm{{{labels}}} {prompt}",
        "# HELP aasp_predicted_completion_tpm max completion_tpm over AASP prediction window (leader only; followers 0)",
        "# TYPE aasp_predicted_completion_tpm gauge",
        f"aasp_predicted_completion_tpm{{{labels}}} {completion}",
        "# HELP aasp_predicted_total_tpm max total_tpm over AASP prediction window (leader only; followers 0)",
        "# TYPE aasp_predicted_total_tpm gauge",
        f"aasp_predicted_total_tpm{{{labels}}} {total}",
        "# HELP aasp_predicted_latency_ms max latency over AASP prediction window (leader only; followers 0)",
        "# TYPE aasp_predicted_latency_ms gauge",
        f"aasp_predicted_latency_ms{{{labels}}} {latency}",
        "# HELP aasp_adapter_up 1 if leader and last AASP fetch succeeded",
        "# TYPE aasp_adapter_up gauge",
        f"aasp_adapter_up{{{labels}}} {up}",
        "# HELP aasp_adapter_is_leader 1 if this pod holds the metrics lease",
        "# TYPE aasp_adapter_is_leader gauge",
        f"aasp_adapter_is_leader{{{labels}}} {1 if leader else 0}",
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
            if is_leader():
                fetch_once()
            else:
                LOG.debug("follower: skip AASP poll")
        except Exception:
            LOG.exception("unexpected error in poll loop")
            apply_peaks(0, 0, 0, error="unexpected poll error")
        time.sleep(POLL_SECONDS)


def _resolve_namespace() -> str:
    if POD_NAMESPACE:
        return POD_NAMESPACE
    ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    if os.path.exists(ns_path):
        with open(ns_path, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def main() -> None:
    global _election

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOG.info(
        "starting adapter mock=%s port=%s poll=%ss window=%sm base=%s "
        "leader_election=%s iam_auto_refresh=%s",
        MOCK,
        METRICS_PORT,
        POLL_SECONDS,
        WINDOW_MINUTES,
        BASE_URL,
        LEADER_ELECTION,
        iam_auto_refresh_enabled(),
    )

    if LEADER_ELECTION:
        identity = POD_NAME or os.environ.get("HOSTNAME", "")
        namespace = _resolve_namespace()
        if not identity or not namespace:
            raise SystemExit(
                "LEADER_ELECTION=1 requires POD_NAME (or HOSTNAME) and POD_NAMESPACE"
            )
        _election = LeaseLeaderElection(
            identity=identity,
            namespace=namespace,
            lease_name=LEASE_NAME,
            lease_duration_seconds=LEASE_DURATION_SECONDS,
            renew_interval_seconds=LEASE_RENEW_SECONDS,
        )
        _election.start()
        # Wait briefly for first election tick so startup metrics are coherent.
        deadline = time.time() + max(LEASE_RENEW_SECONDS * 2, 3.0)
        while time.time() < deadline and not is_leader():
            time.sleep(0.2)
        if is_leader():
            fetch_once()
        else:
            LOG.info("started as follower; waiting to acquire lease before polling AASP")
    else:
        fetch_once()

    threading.Thread(target=poll_loop, name="aasp-poller", daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", METRICS_PORT), MetricsHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
