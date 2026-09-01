"""Kubernetes Lease-based leader election (in-cluster, stdlib only)."""

from __future__ import annotations

import json
import logging
import os
import ssl
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOG = logging.getLogger("aasp-metrics-adapter.leader")

TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
NS_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _utc_now_rfc3339() -> str:
    # Kubernetes microtime-friendly RFC3339.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class LeaseLeaderElection:
    """Compete for a coordination.k8s.io/v1 Lease; expose is_leader()."""

    def __init__(
        self,
        identity: str,
        namespace: str,
        lease_name: str,
        lease_duration_seconds: int = 15,
        renew_interval_seconds: float = 5.0,
        api_host: str | None = None,
        api_port: str | None = None,
    ) -> None:
        self.identity = identity
        self.namespace = namespace
        self.lease_name = lease_name
        self.lease_duration_seconds = lease_duration_seconds
        self.renew_interval_seconds = renew_interval_seconds
        self._api_host = api_host or os.environ.get("KUBERNETES_SERVICE_HOST", "")
        self._api_port = api_port or os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        self._lock = threading.Lock()
        self._is_leader = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._token = _read_file(TOKEN_PATH)
        self._ssl = ssl.create_default_context(cafile=CA_PATH)

    @property
    def enabled(self) -> bool:
        return bool(self._api_host and self.identity and self.namespace)

    def is_leader(self) -> bool:
        with self._lock:
            return self._is_leader

    def _set_leader(self, value: bool) -> None:
        with self._lock:
            changed = self._is_leader != value
            self._is_leader = value
        if changed:
            LOG.info("leader=%s identity=%s lease=%s/%s", value, self.identity, self.namespace, self.lease_name)

    def _lease_url(self) -> str:
        return (
            f"https://{self._api_host}:{self._api_port}"
            f"/apis/coordination.k8s.io/v1/namespaces/{self.namespace}/leases/{self.lease_name}"
        )

    def _request(self, method: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(self._lease_url(), data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=10, context=self._ssl) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"message": raw}
            return exc.code, payload

    def _holder(self, lease: dict[str, Any]) -> str:
        return ((lease.get("spec") or {}).get("holderIdentity")) or ""

    def _renew_time(self, lease: dict[str, Any]) -> datetime | None:
        raw = (lease.get("spec") or {}).get("renewTime")
        if not raw or not isinstance(raw, str):
            return None
        # Accept both Z and +00:00.
        text = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _lease_expired(self, lease: dict[str, Any]) -> bool:
        renew = self._renew_time(lease)
        if renew is None:
            return True
        age = (datetime.now(timezone.utc) - renew.astimezone(timezone.utc)).total_seconds()
        duration = (lease.get("spec") or {}).get("leaseDurationSeconds") or self.lease_duration_seconds
        return age > float(duration)

    def _try_acquire_or_renew(self) -> None:
        code, lease = self._request("GET")
        now = _utc_now_rfc3339()

        if code == 404:
            body = {
                "apiVersion": "coordination.k8s.io/v1",
                "kind": "Lease",
                "metadata": {"name": self.lease_name, "namespace": self.namespace},
                "spec": {
                    "holderIdentity": self.identity,
                    "leaseDurationSeconds": self.lease_duration_seconds,
                    "acquireTime": now,
                    "renewTime": now,
                    "leaseTransitions": 1,
                },
            }
            # POST create
            create_url = (
                f"https://{self._api_host}:{self._api_port}"
                f"/apis/coordination.k8s.io/v1/namespaces/{self.namespace}/leases"
            )
            data = json.dumps(body).encode("utf-8")
            req = Request(
                create_url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urlopen(req, timeout=10, context=self._ssl) as resp:
                    if 200 <= resp.status < 300:
                        self._set_leader(True)
                        return
            except HTTPError as exc:
                if exc.code != 409:
                    LOG.warning("create lease failed: HTTP %s", exc.code)
                # Race: someone else created it; retry next tick.
                self._set_leader(False)
                return
            except URLError as exc:
                LOG.warning("create lease failed: %s", exc)
                self._set_leader(False)
                return
            self._set_leader(False)
            return

        if code != 200:
            LOG.warning("get lease failed: HTTP %s %s", code, lease)
            # Keep previous leadership optimistic only if we still think we hold it;
            # safer to drop leadership on API errors after a miss would be complex —
            # drop to avoid dual leaders if API is flaky for long.
            return

        holder = self._holder(lease)
        expired = self._lease_expired(lease)
        resource_version = (lease.get("metadata") or {}).get("resourceVersion")

        if holder == self.identity or expired or holder == "":
            transitions = int((lease.get("spec") or {}).get("leaseTransitions") or 0)
            acquire = (lease.get("spec") or {}).get("acquireTime") or now
            if holder != self.identity:
                transitions += 1
                acquire = now
            patch = {
                "apiVersion": "coordination.k8s.io/v1",
                "kind": "Lease",
                "metadata": {
                    "name": self.lease_name,
                    "namespace": self.namespace,
                    "resourceVersion": resource_version,
                },
                "spec": {
                    "holderIdentity": self.identity,
                    "leaseDurationSeconds": self.lease_duration_seconds,
                    "acquireTime": acquire,
                    "renewTime": now,
                    "leaseTransitions": transitions,
                },
            }
            put_code, put_body = self._request("PUT", patch)
            if put_code in (200, 201):
                self._set_leader(True)
            else:
                LOG.debug("renew/acquire failed: HTTP %s %s", put_code, put_body)
                self._set_leader(False)
            return

        # Someone else holds a valid lease.
        self._set_leader(False)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._try_acquire_or_renew()
            except Exception:
                LOG.exception("leader election tick failed")
            self._stop.wait(self.renew_interval_seconds)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="lease-leader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
