from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Capability:
    type: str
    instance: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Capability":
        return cls(
            type=raw.get("type", ""),
            instance=raw.get("instance", ""),
            parameters=raw.get("parameters") or {},
        )


@dataclass(slots=True)
class Device:
    sku: str
    device_id: str
    name: str
    capabilities: list[Capability] = field(default_factory=list)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Device":
        return cls(
            sku=raw.get("sku", ""),
            device_id=raw.get("device", ""),
            name=raw.get("deviceName") or raw.get("device", ""),
            capabilities=[
                Capability.from_api(c)
                for c in raw.get("capabilities", [])
            ],
        )

    def has(self, capability_type: str, instance: str) -> bool:
        return any(
            c.type == capability_type and c.instance == instance
            for c in self.capabilities
        )


@dataclass(slots=True)
class RequestMetric:
    operation: str
    ok: bool
    latency_ms: float
    device_name: str | None = None
    sku: str | None = None
    device_id: str | None = None
    online: bool | None = None
    http_status: int | None = None
    error: str | None = None
