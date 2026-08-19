from __future__ import annotations

import time
import uuid
from typing import Any

import requests

from .errors import GoveeApiError


class GoveeClient:
    BASE_URL = "https://openapi.api.govee.com/router/api/v1"

    def __init__(self, api_key: str, timeout: float = 8.0):
        if not api_key:
            raise ValueError("GOVEE_API_KEY is required")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Govee-API-Key": api_key,
            "Content-Type": "application/json",
        })

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], float, int]:
        started = time.perf_counter()
        try:
            response = self.session.request(
                method,
                f"{self.BASE_URL}{path}",
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            latency = (time.perf_counter() - started) * 1000
            raise GoveeApiError(
                f"Network error after {latency:.1f} ms: {exc}"
            ) from exc

        latency = (time.perf_counter() - started) * 1000

        try:
            data = response.json()
        except ValueError as exc:
            raise GoveeApiError(
                f"HTTP {response.status_code}: non-JSON response"
            ) from exc

        if not response.ok:
            raise GoveeApiError(
                f"HTTP {response.status_code}: "
                f"{data.get('message') or data.get('msg') or data}"
            )

        code = data.get("code")
        if code not in (None, 200):
            raise GoveeApiError(
                f"Govee code {code}: "
                f"{data.get('message') or data.get('msg') or data}"
            )

        return data, latency, response.status_code

    def get_devices(self) -> tuple[list[dict[str, Any]], float, int]:
        data, latency, status = self._request("GET", "/user/devices")
        return data.get("data") or [], latency, status

    def get_state(
        self,
        sku: str,
        device_id: str,
    ) -> tuple[dict[str, Any], float, int]:
        body = {
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": sku,
                "device": device_id,
            },
        }
        data, latency, status = self._request(
            "POST", "/device/state", json_body=body
        )
        return data.get("payload") or {}, latency, status

    def control(
        self,
        sku: str,
        device_id: str,
        capability_type: str,
        instance: str,
        value: Any,
    ) -> tuple[dict[str, Any], float, int]:
        body = {
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": sku,
                "device": device_id,
                "capability": {
                    "type": capability_type,
                    "instance": instance,
                    "value": value,
                },
            },
        }
        data, latency, status = self._request(
            "POST", "/device/control", json_body=body
        )
        return data, latency, status

    def get_scenes(self, sku: str, device_id: str) -> tuple[dict[str, Any], float, int]:
        """Query dynamic scenes for a device (POST /device/scenes).

        Returns the payload dict (may include capabilities with dynamic_scene options),
        the latency in ms and the HTTP status code.
        """
        body = {
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": sku,
                "device": device_id,
            },
        }
        data, latency, status = self._request(
            "POST", "/device/scenes", json_body=body
        )
        return data.get("payload") or {}, latency, status
