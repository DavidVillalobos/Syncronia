from __future__ import annotations

from .device_registry import DeviceRegistry
from .errors import UnsupportedCapabilityError
from .govee_client import GoveeClient
from .models import Device


class LightController:
    def __init__(self, client: GoveeClient, registry: DeviceRegistry):
        self.client = client
        self.registry = registry

    @staticmethod
    def _require(device: Device, capability_type: str, instance: str) -> None:
        if not device.has(capability_type, instance):
            raise UnsupportedCapabilityError(
                f"{device.name} ({device.sku}) does not expose "
                f"{capability_type} -> {instance}"
            )

    def power(self, device_query: str, on: bool):
        device = self.registry.resolve(device_query)
        cap = "devices.capabilities.on_off"
        self._require(device, cap, "powerSwitch")
        return self.client.control(
            device.sku, device.device_id,
            cap, "powerSwitch", 1 if on else 0
        )

    def brightness(self, device_query: str, value: int):
        if not 0 <= value <= 100:
            raise ValueError("brightness must be 0..100")
        device = self.registry.resolve(device_query)
        cap = "devices.capabilities.range"
        self._require(device, cap, "brightness")
        return self.client.control(
            device.sku, device.device_id,
            cap, "brightness", value
        )

    def color(self, device_query: str, r: int, g: int, b: int):
        for n in (r, g, b):
            if not 0 <= n <= 255:
                raise ValueError("RGB values must be 0..255")

        device = self.registry.resolve(device_query)
        cap = "devices.capabilities.color_setting"
        self._require(device, cap, "colorRgb")

        # Govee colorRgb uses packed integer RGB:
        # (R << 16) | (G << 8) | B
        value = (r << 16) | (g << 8) | b

        return self.client.control(
            device.sku, device.device_id,
            cap, "colorRgb", value
        )

    def segment_color(self, device_query: str, segments: list[dict]):
        """Set colors for specific segments on segmented devices.

        Accepts list of segment descriptors produced by the CLI, e.g.
            [{"startIndex": 0, "endIndex": 0, "colorRgb": <int>}, ...]
        or
            [{"segment": [0,1,2], "rgb": <int>}, ...]

        Many Govee devices expect a payload shaped like:
            {"segment": [0,1,2], "rgb": 16711680}
        where "segment" is an array of integer indices and "rgb" is a packed
        integer (R<<16 | G<<8 | B). Because the API often accepts a single
        rgb for a list of segments, the method groups provided segment
        descriptors by color and sends one control call per color group.

        Returns the last (data, latency, status) tuple from the calls.
        """
        device = self.registry.resolve(device_query)
        cap = "devices.capabilities.segment_color_setting"
        instance = "segmentedColorRgb"
        self._require(device, cap, instance)

        # Find capability parameters if available
        cap_obj = next(
            (c for c in device.capabilities if c.type == cap and c.instance == instance),
            None
        )
        params = cap_obj.parameters if cap_obj else {}

        # Helper to expand a segment descriptor into a list of indices
        def expand_indices(seg: dict) -> list[int]:
            if "segment" in seg and isinstance(seg["segment"], list):
                return list(seg["segment"])
            if "startIndex" in seg and "endIndex" in seg:
                return list(range(int(seg["startIndex"]), int(seg["endIndex"]) + 1))
            if "start" in seg and "end" in seg:
                return list(range(int(seg["start"]), int(seg["end"]) + 1))
            if "index" in seg:
                return [int(seg["index"])]
            raise ValueError("segment descriptor must include segment/list or startIndex/endIndex or index")

        # Normalize input and group by color (rgb)
        groups: dict[int, list[int]] = {}

        for seg in segments:
            if not isinstance(seg, dict):
                raise ValueError("each segment must be a dict")

            # Accept both colorRgb and rgb keys from callers
            color = seg.get("colorRgb") if seg.get("colorRgb") is not None else seg.get("rgb")
            if color is None:
                raise ValueError("segment descriptor missing colorRgb or rgb")
            try:
                color = int(color)
            except Exception:
                raise ValueError("color must be an integer packed RGB")

            idxs = expand_indices(seg)
            if not idxs:
                continue

            # Optionally validate indices against parameters
            try:
                for field in params.get("fields", []):
                    if field.get("fieldName") == "segment":
                        er = field.get("elementRange") or {}
                        min_idx = er.get("min")
                        max_idx = er.get("max")
                        if min_idx is not None and any(i < min_idx for i in idxs):
                            raise ValueError(f"segment index below min {min_idx}")
                        if max_idx is not None and any(i > max_idx for i in idxs):
                            raise ValueError(f"segment index above max {max_idx}")
            except Exception:
                # If validation fails, surface the error
                raise

            groups.setdefault(color, []).extend(idxs)

        last_result = None
        # Send one control call per color group
        for color, idx_list in groups.items():
            unique_idxs = sorted(set(idx_list))
            payload = {"segment": unique_idxs, "rgb": int(color)}
            last_result = self.client.control(device.sku, device.device_id, cap, instance, payload)

        if last_result is None:
            raise ValueError("no segments to set")
        return last_result

    def segment_brightness(self, device_query: str, segments: list[dict]):
        """Set brightness for specific segments on segmented devices.

        Accepts descriptors like {"startIndex":0,"endIndex":2,"brightness":50}
        or {"segment":[0,1],"brightness":80}.

        Many Govee devices expect:
            {"segment": [0,1], "brightness": 80}

        The method groups descriptors by brightness value and sends one control
        call per brightness group. Returns the last (data, latency, status).
        """
        device = self.registry.resolve(device_query)
        cap = "devices.capabilities.segment_color_setting"
        instance = "segmentedBrightness"
        self._require(device, cap, instance)

        cap_obj = next(
            (c for c in device.capabilities if c.type == cap and c.instance == instance),
            None
        )
        params = cap_obj.parameters if cap_obj else {}

        def expand_indices(seg: dict) -> list[int]:
            if "segment" in seg and isinstance(seg["segment"], list):
                return list(seg["segment"])
            if "startIndex" in seg and "endIndex" in seg:
                return list(range(int(seg["startIndex"]), int(seg["endIndex"]) + 1))
            if "start" in seg and "end" in seg:
                return list(range(int(seg["start"]), int(seg["end"]) + 1))
            if "index" in seg:
                return [int(seg["index"])]
            raise ValueError("segment descriptor must include segment/list or startIndex/endIndex or index")

        groups: dict[int, list[int]] = {}

        for seg in segments:
            if not isinstance(seg, dict):
                raise ValueError("each segment must be a dict")
            bright = seg.get("brightness")
            if bright is None:
                raise ValueError("segment descriptor missing brightness")
            bright = int(bright)
            if not (0 <= bright <= 100):
                raise ValueError("brightness must be 0..100")

            idxs = expand_indices(seg)

            # Optional validation against params
            try:
                for field in params.get("fields", []):
                    if field.get("fieldName") == "segment":
                        er = field.get("elementRange") or {}
                        min_idx = er.get("min")
                        max_idx = er.get("max")
                        if min_idx is not None and any(i < min_idx for i in idxs):
                            raise ValueError(f"segment index below min {min_idx}")
                        if max_idx is not None and any(i > max_idx for i in idxs):
                            raise ValueError(f"segment index above max {max_idx}")
            except Exception:
                raise

            groups.setdefault(bright, []).extend(idxs)

        last_result = None
        for bright, idx_list in groups.items():
            unique_idxs = sorted(set(idx_list))
            payload = {"segment": unique_idxs, "brightness": int(bright)}
            last_result = self.client.control(device.sku, device.device_id, cap, instance, payload)

        if last_result is None:
            raise ValueError("no segments to set")
        return last_result

    def plan_scene_calls(self, device_query: str, scene: dict) -> list[dict]:
        """Given a scene specification (dict), return a plan: list of planned control calls
        without executing them. Each plan item is a dict with keys: cap, instance, payload.

        Scene format supported (flexible):
          {
            "colors": [{"index":"0"|"0-3"|[0,1], "rgb": [R,G,B] or int}, ...],
            "brightness": [{"index":..., "brightness": 80}, ...]
          }
        """
        device = self.registry.resolve(device_query)
        plan: list[dict] = []

        # helper to parse an index spec into list of ints
        def parse_index_spec(idx_spec):
            if isinstance(idx_spec, list):
                return list(map(int, idx_spec))
            if isinstance(idx_spec, int):
                return [int(idx_spec)]
            if isinstance(idx_spec, str):
                if "-" in idx_spec:
                    a, b = idx_spec.split("-")
                    return list(range(int(a), int(b) + 1))
                return [int(idx_spec)]
            raise ValueError("invalid index spec")

        # Colors
        for c in scene.get("colors", []):
            idxs = parse_index_spec(c.get("index") or c.get("segment") or c.get("startIndex"))
            rgb = c.get("rgb") if c.get("rgb") is not None else c.get("colorRgb")
            if isinstance(rgb, list):
                r, g, b = rgb
                rgb_val = (int(r) << 16) | (int(g) << 8) | int(b)
            else:
                rgb_val = int(rgb)
            plan.append({
                "cap": "devices.capabilities.segment_color_setting",
                "instance": "segmentedColorRgb",
                "payload": {"segment": idxs, "rgb": rgb_val},
            })

        # Brightness
        for b in scene.get("brightness", []):
            idxs = parse_index_spec(b.get("index") or b.get("segment") or b.get("startIndex"))
            bright = int(b.get("brightness"))
            plan.append({
                "cap": "devices.capabilities.segment_color_setting",
                "instance": "segmentedBrightness",
                "payload": {"segment": idxs, "brightness": bright},
            })

        return plan

    def dry_run_scene(self, device_query: str, scene: dict) -> list[dict]:
        """Return a human-readable plan for the scene without executing network calls."""
        # just reuse plan_scene_calls and annotate by resolving capability instances
        device = self.registry.resolve(device_query)
        plan = self.plan_scene_calls(device_query, scene)
        # enrich with capability presence
        for item in plan:
            cap = item["cap"]
            inst = item["instance"]
            item["supported"] = device.has(cap, inst)
        return plan

    def apply_scene(self, device_query: str, scene: dict, use_diy_if_supported: bool = True):
        """Attempt to apply a scene. If the device supports dynamic DIY scenes, try that first.
        Otherwise fall back to executing the planned control calls.

        Returns list of results from client.control calls executed.
        """
        device = self.registry.resolve(device_query)
        results = []

        # If device supports diyScene, attempt to call it directly (best-effort)
        if use_diy_if_supported and device.has("devices.capabilities.dynamic_scene", "diyScene"):
            try:
                # The exact payload accepted by Govee for creating/executing a DIY scene
                # is not strictly documented here; attempt a best-effort call passing
                # the scene dict under a 'diyScene' key. If the API rejects this, we'll
                # catch and fall back to explicit segment calls.
                payload = {"diyScene": scene}
                res = self.client.control(device.sku, device.device_id, "devices.capabilities.dynamic_scene", "diyScene", payload)
                results.append(res)
                return results
            except Exception:
                # fall back to manual calls
                pass

        plan = self.plan_scene_calls(device_query, scene)
        for item in plan:
            res = self.client.control(device.sku, device.device_id, item["cap"], item["instance"], item["payload"])
            results.append(res)
        return results

    def list_dynamic_scenes(self, device_query: str) -> list[dict]:
        """Return dynamic scene capability instances and any enumerated options.

        Uses the device's capabilities to list available dynamic_scene instances
        and their parameters (including options like snapshots). Does not call the network.
        """
        device = self.registry.resolve(device_query)
        scenes = []
        for c in device.capabilities:
            if c.type == "devices.capabilities.dynamic_scene":
                item = {
                    "instance": c.instance,
                    "parameters": c.parameters,
                }
                # If parameters contain options, surface them nicely
                opts = c.parameters.get("options") if isinstance(c.parameters, dict) else None
                if opts:
                    item["options"] = opts
                scenes.append(item)
        return scenes

    def get_dynamic_scenes(self, device_query: str) -> list[dict]:
        """Query the POST /device/scenes endpoint for a device and return dynamic_scene entries.

        Returns a list of capability entries similar to list_dynamic_scenes but sourced from the
        scenes endpoint; options values may be objects (paramId/id) — caller must pass the
        same object to activate_dynamic_scene.
        """
        device = self.registry.resolve(device_query)
        payload, latency, status = self.client.get_scenes(device.sku, device.device_id)
        caps = payload.get("capabilities") if isinstance(payload, dict) else []
        scenes = []
        for c in caps:
            if c.get("type") == "devices.capabilities.dynamic_scene":
                item = {
                    "instance": c.get("instance"),
                    "parameters": c.get("parameters"),
                }
                opts = c.get("parameters", {}).get("options") if isinstance(c.get("parameters"), dict) else None
                if opts:
                    item["options"] = opts
                scenes.append(item)
        return scenes

    def activate_dynamic_scene(self, device_query: str, instance: str, value):
        """Activate a dynamic scene instance on the device by sending the provided value.

        Example: instance='snapshot', value=2571559 (an integer option value observed in capabilities)
        Returns the client.control result tuple.
        """
        device = self.registry.resolve(device_query)
        cap = "devices.capabilities.dynamic_scene"
        # value can be int or dict depending on instance; pass through
        return self.client.control(device.sku, device.device_id, cap, instance, value)
