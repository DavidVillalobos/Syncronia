from __future__ import annotations

import time

from .device_registry import DeviceRegistry
from .govee_client import GoveeClient
from .models import Device, RequestMetric
from .stats import StatsStore


def flatten_state(payload: dict) -> dict:
    result = {}
    for cap in payload.get("capabilities", []):
        key = f"{cap.get('type')}::{cap.get('instance')}"
        state = cap.get("state") or {}
        result[key] = state.get("value")
    return result


def online_from_state(payload: dict) -> bool | None:
    for cap in payload.get("capabilities", []):
        if cap.get("type") == "devices.capabilities.online":
            state = cap.get("state") or {}
            value = state.get("value")
            if isinstance(value, bool):
                return value
            if value in (0, 1):
                return bool(value)
    return None


class DiagnosticsService:
    def __init__(
        self,
        client: GoveeClient,
        registry: DeviceRegistry,
        stats: StatsStore,
    ):
        self.client = client
        self.registry = registry
        self.stats = stats

    def state(self, device_query: str) -> dict:
        device = self.registry.resolve(device_query)

        try:
            payload, latency, http_status = self.client.get_state(
                device.sku, device.device_id
            )
            online = online_from_state(payload)
            self.stats.record(RequestMetric(
                operation="state",
                ok=True,
                latency_ms=latency,
                device_name=device.name,
                sku=device.sku,
                device_id=device.device_id,
                online=online,
                http_status=http_status,
            ))
            return {
                "device": device,
                "online": online,
                "latency_ms": latency,
                "state": flatten_state(payload),
                "raw": payload,
            }
        except Exception as exc:
            self.stats.record(RequestMetric(
                operation="state",
                ok=False,
                latency_ms=0,
                device_name=device.name,
                sku=device.sku,
                device_id=device.device_id,
                error=str(exc),
            ))
            raise

    def health(
        self,
        device_query: str,
        samples: int = 3,
        interval: float = 0.35,
    ) -> dict:
        if samples < 1 or samples > 10:
            raise ValueError("samples must be 1..10")

        readings = []
        errors = []

        for i in range(samples):
            try:
                readings.append(self.state(device_query))
            except Exception as exc:
                errors.append(str(exc))
            if i < samples - 1:
                time.sleep(interval)

        successful = len(readings)
        latencies = [r["latency_ms"] for r in readings]
        online_values = [
            r["online"] for r in readings if r["online"] is not None
        ]

        return {
            "samples": samples,
            "successful": successful,
            "failed": len(errors),
            "success_rate": successful / samples * 100,
            "online": (
                all(online_values)
                if online_values else None
            ),
            "avg_latency_ms": (
                sum(latencies) / len(latencies)
                if latencies else None
            ),
            "min_latency_ms": min(latencies) if latencies else None,
            "max_latency_ms": max(latencies) if latencies else None,
            "errors": errors,
        }

    def doctor(self) -> list[dict]:
        devices = self.registry.refresh()
        report = []

        for device in devices:
            try:
                result = self.health(device.device_id, samples=1)
                report.append({
                    "name": device.name,
                    "sku": device.sku,
                    "ok": result["successful"] == 1,
                    "online": result["online"],
                    "latency_ms": result["avg_latency_ms"],
                    "error": None,
                })
            except Exception as exc:
                report.append({
                    "name": device.name,
                    "sku": device.sku,
                    "ok": False,
                    "online": None,
                    "latency_ms": None,
                    "error": str(exc),
                })
        return report
