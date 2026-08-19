from __future__ import annotations

from .errors import AmbiguousDeviceError, DeviceNotFoundError
from .govee_client import GoveeClient
from .models import Device


class DeviceRegistry:
    def __init__(self, client: GoveeClient):
        self.client = client
        self._devices: list[Device] | None = None

    def refresh(self) -> list[Device]:
        raw_devices, _, _ = self.client.get_devices()
        self._devices = [Device.from_api(d) for d in raw_devices]
        return self._devices

    def all(self, refresh: bool = False) -> list[Device]:
        if refresh or self._devices is None:
            return self.refresh()
        return self._devices

    def resolve(self, query: str) -> Device:
        q = query.casefold().strip()
        devices = self.all()

        exact = [
            d for d in devices
            if d.name.casefold() == q
            or d.device_id.casefold() == q
        ]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise AmbiguousDeviceError(
                f"More than one exact match for {query!r}"
            )

        partial = [
            d for d in devices
            if q in d.name.casefold()
            or q in d.sku.casefold()
        ]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            names = ", ".join(f"{d.name} ({d.sku})" for d in partial)
            raise AmbiguousDeviceError(
                f"Ambiguous device {query!r}: {names}"
            )

        raise DeviceNotFoundError(f"Device not found: {query}")
