from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .controller import LightController
from .device_registry import DeviceRegistry
from .diagnostics import DiagnosticsService
from .govee_client import GoveeClient
from .stats import StatsStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="light-engine",
        description="Modular Govee lighting controller"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices")

    p_caps = sub.add_parser("capabilities")
    p_caps.add_argument("device")

    p_status = sub.add_parser("status")
    p_status.add_argument("device")
    p_status.add_argument("--raw", action="store_true")

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("device")
    p_inspect.add_argument("--raw", action="store_true", help="Also fetch raw state payload")

    p_health = sub.add_parser("health")
    p_health.add_argument("device")
    p_health.add_argument("--samples", type=int, default=3)

    sub.add_parser("doctor")

    p_stats = sub.add_parser("stats")
    p_stats.add_argument("device", nargs="?")

    p_action = sub.add_parser("action")
    p_action.add_argument("device")
    p_action.add_argument(
        "action",
        choices=[
            "on", "off", "brightness", "color",
            "segcolor", "segbrightness",
        ]
    )
    p_action.add_argument("values", nargs="*")

    # scene commands: dry-run and run
    p_scene = sub.add_parser("scene", help="Apply or inspect scenes")
    p_scene.add_argument("mode", choices=["dry-run", "run"], help="dry-run to preview payloads, run to execute")
    p_scene.add_argument("device")
    p_scene.add_argument("scene_file", help="Path to JSON scene file")
    p_scene.add_argument("--use-diy", action="store_true", help="Attempt to use device's diyScene capability when running")

    p_scenes = sub.add_parser("scenes", help="List or invoke device dynamic scenes (snapshots, diy)")
    p_scenes.add_argument("device", nargs="?", help="Device or entity to inspect (optional with --all)")
    p_scenes.add_argument("--all", action="store_true", help="List scenes for all known entities")
    p_scenes.add_argument("--invoke", nargs=2, metavar=("INSTANCE", "VALUE"), help="Invoke an instance with a given value, e.g. --invoke snapshot 2571559")
    p_scenes.add_argument("--invoke-by-name", nargs=2, metavar=("INSTANCE", "NAME"), help='Invoke an instance by option name (partial, case-insensitive) e.g. --invoke-by-name snapshot "Warm Light"')
    p_scenes.add_argument("--verbose", action="store_true", help="Show full parameters (long output)")
    p_scenes.add_argument("--dynamic", action="store_true", help="Query the dynamic scenes endpoint (POST /device/scenes) for the device")
    p_scenes.add_argument("--broadcast-by-name", nargs=2, metavar=("INSTANCE","NAME"), help="Find all entities that expose INSTANCE with option NAME (partial) and invoke in parallel")
    p_scenes.add_argument("--broadcast-dynamic", nargs=1, metavar=("NAME"), help="Search dynamic scenes (POST /device/scenes) across all entities for NAME (partial) and invoke matches in parallel")

    return parser


def mask_device_id(device_id: str) -> str:
    if len(device_id) < 8:
        return "***"
    return f"{device_id[:5]}...{device_id[-5:]}"


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()

    try:
        api_key = os.environ["GOVEE_API_KEY"]
    except KeyError:
        print("ERROR: set GOVEE_API_KEY first.", file=sys.stderr)
        raise SystemExit(2)

    client = GoveeClient(api_key)
    registry = DeviceRegistry(client)
    controller = LightController(client, registry)
    stats = StatsStore()
    diagnostics = DiagnosticsService(client, registry, stats)

    try:
        if args.command == "devices":
            for d in registry.refresh():
                print(
                    f"{d.name:28} {d.sku:8} "
                    f"{mask_device_id(d.device_id):16} "
                    f"{len(d.capabilities)} capabilities"
                )

        elif args.command == "capabilities":
            d = registry.resolve(args.device)
            print(f"{d.name} ({d.sku})")
            for c in d.capabilities:
                print(f"  {c.type} -> {c.instance}")
                if c.parameters:
                    import json
                    print("    parameters:")
                    for line in json.dumps(c.parameters, indent=2).splitlines():
                        print(f"      {line}")

        elif args.command == "status":
            r = diagnostics.state(args.device)
            print(f"Device:  {r['device'].name} ({r['device'].sku})")
            print(f"Online:  {r['online']}")
            print(f"Latency: {r['latency_ms']:.1f} ms")
            if args.raw:
                import json
                print(json.dumps(r["raw"], indent=2))
            else:
                for key, value in r["state"].items():
                    print(f"  {key} = {value}")

        elif args.command == "inspect":
            # Detailed inspection: capabilities + optional raw state
            d = registry.resolve(args.device)
            print(f"Device: {d.name} ({d.sku}) id={mask_device_id(d.device_id)}")
            import json
            print("Capabilities:")
            for c in d.capabilities:
                print(f"  {c.type} -> {c.instance}")
                if c.parameters:
                    print("    parameters:")
                    for line in json.dumps(c.parameters, indent=2).splitlines():
                        print(f"      {line}")
            if args.raw:
                try:
                    r = diagnostics.state(args.device)
                    print("\nRaw state payload:")
                    print(json.dumps(r["raw"], indent=2))

                    # Try to infer segments from raw state
                    payload = r["raw"]
                    found = False
                    for cap in payload.get("capabilities", []):
                        if cap.get("type") == "devices.capabilities.segment_color_setting":
                            found = True
                            state = cap.get("state") or {}
                            val = state.get("value")
                            if isinstance(val, dict) and "segments" in val:
                                segs = val.get("segments") or []
                                print("\nObserved segments in state:")
                                for s in segs:
                                    print("  ", s)
                            else:
                                print("\nNo explicit 'segments' list observed in state for segment_color_setting")
                    if not found:
                        print("\nNo segment_color_setting entry found in raw state.")
                except Exception as exc:
                    print(f"Failed to fetch raw state: {exc}")

        elif args.command == "health":
            r = diagnostics.health(args.device, samples=args.samples)
            print(f"Successful: {r['successful']}/{r['samples']}")
            print(f"Success:    {r['success_rate']:.1f}%")
            print(f"Online:     {r['online']}")
            if r["avg_latency_ms"] is not None:
                print(
                    "Latency:    "
                    f"avg={r['avg_latency_ms']:.1f} ms "
                    f"min={r['min_latency_ms']:.1f} ms "
                    f"max={r['max_latency_ms']:.1f} ms"
                )
            for error in r["errors"]:
                print(f"ERROR: {error}")

        elif args.command == "doctor":
            report = diagnostics.doctor()
            for r in report:
                mark = "OK" if r["ok"] else "FAIL"
                online = "online" if r["online"] else (
                    "offline" if r["online"] is False else "unknown"
                )
                latency = (
                    f"{r['latency_ms']:.1f} ms"
                    if r["latency_ms"] is not None else "-"
                )
                print(
                    f"{mark:4} {r['name']:28} {r['sku']:8} "
                    f"{online:8} {latency}"
                )
                if r["error"]:
                    print(f"     {r['error']}")

        elif args.command == "stats":
            rows = stats.summary(args.device)
            if not rows:
                print("No stats recorded yet.")
            for r in rows:
                avg = (
                    f"{r['avg_latency_ms']:.1f} ms"
                    if r["avg_latency_ms"] is not None else "-"
                )
                print(
                    f"{r['device']:28} "
                    f"samples={r['samples']:4} "
                    f"success={r['success_rate']:6.1f}% "
                    f"avg={avg:10} "
                    f"online={r['last_online']}"
                )

        elif args.command == "action":
            if args.action == "on":
                _, latency, _ = controller.power(args.device, True)
            elif args.action == "off":
                _, latency, _ = controller.power(args.device, False)
            elif args.action == "brightness":
                if len(args.values) != 1:
                    raise ValueError("brightness needs one value: 0..100")
                _, latency, _ = controller.brightness(
                    args.device, int(args.values[0])
                )
            elif args.action == "color":
                if len(args.values) != 3:
                    raise ValueError("color needs R G B")
                r, g, b = map(int, args.values)
                _, latency, _ = controller.color(
                    args.device, r, g, b
                )
            elif args.action == "segcolor":
                # Values: one or more tokens like "IDX:R:G:B" or range "A-B:R:G:B"
                if len(args.values) < 1:
                    raise ValueError(
                        "segcolor needs one or more segments as INDEX:R:G:B or RANGE:R:G:B"
                    )
                segments = []
                for tok in args.values:
                    # split into indexpart and colors
                    try:
                        index_part, r_str, g_str, b_str = tok.split(":")
                    except ValueError:
                        raise ValueError("each token must be INDEX:R:G:B or A-B:R:G:B")
                    r, g, b = map(int, (r_str, g_str, b_str))
                    if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
                        raise ValueError("RGB values must be 0..255")

                    if "-" in index_part:
                        a, bidx = index_part.split("-")
                        start = int(a)
                        end = int(bidx)
                    else:
                        start = end = int(index_part)

                    packed = (r << 16) | (g << 8) | b
                    segments.append({
                        "startIndex": start,
                        "endIndex": end,
                        "colorRgb": packed,
                    })
                _, latency, _ = controller.segment_color(args.device, segments)
            elif args.action == "segbrightness":
                # Values: one or more tokens like "IDX:BRIGHT" or range "A-B:BRIGHT"
                if len(args.values) < 1:
                    raise ValueError(
                        "segbrightness needs one or more segments as INDEX:BRIGHT or A-B:BRIGHT"
                    )
                segments = []
                for tok in args.values:
                    try:
                        index_part, b_str = tok.split(":")
                    except ValueError:
                        raise ValueError("each token must be INDEX:BRIGHT or A-B:BRIGHT")
                    bright = int(b_str)
                    if not (0 <= bright <= 100):
                        raise ValueError("brightness must be 0..100")

                    if "-" in index_part:
                        a, bidx = index_part.split("-")
                        start = int(a)
                        end = int(bidx)
                    else:
                        start = end = int(index_part)

                    segments.append({
                        "startIndex": start,
                        "endIndex": end,
                        "brightness": bright,
                    })
                _, latency, _ = controller.segment_brightness(args.device, segments)
            print(f"OK ({latency:.1f} ms)")

        elif args.command == "scene":
            # scene_file is a JSON file with a 'colors' and/or 'brightness' list
            import json
            with open(args.scene_file, "r", encoding="utf-8") as fh:
                scene = json.load(fh)

            if args.mode == "dry-run":
                plan = controller.dry_run_scene(args.device, scene)
                print("Planned control calls:")
                for p in plan:
                    supported = "(supported)" if p.get("supported") else "(unsupported)"
                    print(f"  {p['cap']} -> {p['instance']} {supported}: {p['payload']}")
            else:
                results = controller.apply_scene(args.device, scene, use_diy_if_supported=args.use_diy)
                # results are tuples from client.control: (data, latency_ms, status)
                for res in results:
                    data, latency, status = res
                    print(f"Call returned HTTP {status} in {latency:.1f} ms")
                print("Done")

        elif args.command == "scenes":
            # scenes: either for a single device/entity or --all across registry
            if args.all:
                devices = registry.refresh()
                summary = []
                for d in devices:
                    sc = controller.list_dynamic_scenes(d.device_id)
                    if sc:
                        # compact entries
                        for s in sc:
                            opts = s.get('options') or []
                            if opts:
                                for opt in opts:
                                    summary.append({
                                        "entity": d.name,
                                        "entity_id": d.device_id,
                                        "instance": s['instance'],
                                        "option_name": opt.get('name'),
                                        "option_value": opt.get('value'),
                                    })
                            else:
                                summary.append({
                                    "entity": d.name,
                                    "entity_id": d.device_id,
                                    "instance": s['instance'],
                                    "option_name": None,
                                    "option_value": None,
                                })
                # print compact summary
                if not summary:
                    print("No dynamic scenes found across known entities.")
                else:
                    for item in summary:
                        if item['option_name']:
                            print(f"{item['entity']:24} {item['instance']:12} - {item['option_name']} ({item['option_value']})")
                        else:
                            print(f"{item['entity']:24} {item['instance']:12} - (no options)")
                # done
            elif args.broadcast_by_name:
                instance, name = args.broadcast_by_name
                # find all entities that have this option name (partial match)
                devices = registry.refresh()
                targets = []
                q = name.casefold()
                for d in devices:
                    sc = controller.list_dynamic_scenes(d.device_id)
                    for s in sc:
                        if s['instance'] != instance:
                            continue
                        for opt in (s.get('options') or []):
                            if (opt.get('name') or '').casefold().find(q) != -1:
                                targets.append((d, s['instance'], opt))
                if not targets:
                    print(f"No entities found exposing instance {instance!r} with option matching {name!r}.")
                    raise SystemExit(1)

                # invoke in parallel
                import concurrent.futures
                def invoke_target(t):
                    d, inst, opt = t
                    try:
                        data, latency, status = controller.activate_dynamic_scene(d.device_id, inst, opt.get('value'))
                        return (d.name, inst, opt.get('name'), status, latency, None)
                    except Exception as exc:
                        return (d.name, inst, opt.get('name'), None, None, str(exc))

                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(targets))) as ex:
                    futures = [ex.submit(invoke_target, t) for t in targets]
                    for f in concurrent.futures.as_completed(futures):
                        results.append(f.result())

                # print concise results
                for r in results:
                    name_ent, inst, opt_name, status, latency, err = r
                    if err:
                        print(f"{name_ent:24} {inst:12} {opt_name!r:20} ERROR: {err}")
                    else:
                        print(f"{name_ent:24} {inst:12} {opt_name!r:20} HTTP {status} {latency:.1f} ms")
            elif args.broadcast_dynamic:
                name = args.broadcast_dynamic[0]
                devices = registry.refresh()
                targets = []
                q = name.casefold()
                for d in devices:
                    sc = controller.get_dynamic_scenes(d.device_id)
                    for s in sc:
                        for opt in (s.get('options') or []):
                            if (opt.get('name') or '').casefold().find(q) != -1:
                                targets.append((d, s['instance'], opt))
                if not targets:
                    print(f"No entities found with dynamic scene option matching {name!r}.")
                    raise SystemExit(1)

                import concurrent.futures
                def invoke_target_dynamic(t):
                    d, inst, opt = t
                    try:
                        # pass the value exactly as returned (may be dict)
                        data, latency, status = controller.activate_dynamic_scene(d.device_id, inst, opt.get('value'))
                        return (d.name, inst, opt.get('name'), status, latency, None)
                    except Exception as exc:
                        return (d.name, inst, opt.get('name'), None, None, str(exc))

                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(targets))) as ex:
                    futures = [ex.submit(invoke_target_dynamic, t) for t in targets]
                    for f in concurrent.futures.as_completed(futures):
                        results.append(f.result())

                for r in results:
                    name_ent, inst, opt_name, status, latency, err = r
                    if err:
                        print(f"{name_ent:24} {inst:12} {opt_name!r:20} ERROR: {err}")
                    else:
                        print(f"{name_ent:24} {inst:12} {opt_name!r:20} HTTP {status} {latency:.1f} ms")
            else:
                if not args.device:
                    print("Provide a device name or use --all")
                    raise SystemExit(1)
                # List dynamic_scene capabilities (static) or query dynamic scenes endpoint
                if args.dynamic:
                    scenes = controller.get_dynamic_scenes(args.device)
                else:
                    scenes = controller.list_dynamic_scenes(args.device)
                if args.invoke_by_name:
                    instance, name = args.invoke_by_name
                    # find the instance
                    matches = [s for s in scenes if s['instance'] == instance]
                    if not matches:
                        print(f"No dynamic_scene instance named {instance!r} found. Available instances:")
                        for s in scenes:
                            print(f"  - {s['instance']}")
                        raise SystemExit(1)
                    inst = matches[0]
                    options = inst.get('options') or []
                    # case-insensitive partial match
                    q = name.casefold()
                    found = [opt for opt in options if (opt.get('name') or '').casefold().find(q) != -1]
                    if not found:
                        print(f"No option matching {name!r} for instance {instance!r}. Available options:")
                        for opt in options:
                            print(f"  - name={opt.get('name')!r} value={opt.get('value')!r}")
                        raise SystemExit(1)
                    if len(found) > 1:
                        print(f"Multiple matches for {name!r} in {instance!r}:")
                        for opt in found:
                            print(f"  - name={opt.get('name')!r} value={opt.get('value')!r}")
                        print("Be more specific or use --invoke with the numeric value.")
                        raise SystemExit(1)
                    # single match
                    opt = found[0]
                    val = opt.get('value')
                    data, latency, status = controller.activate_dynamic_scene(args.device, instance, val)
                    print(f"Invoked {instance} -> {opt.get('name')!r} ({val}): HTTP {status} in {latency:.1f} ms")
                elif args.invoke:
                    instance, value = args.invoke
                    # try to parse integer value
                    try:
                        val = int(value)
                    except Exception:
                        val = value
                    data, latency, status = controller.activate_dynamic_scene(args.device, instance, val)
                    print(f"Invoked {instance} -> {val}: HTTP {status} in {latency:.1f} ms")
                elif args.broadcast_by_name:
                    instance, name = args.broadcast_by_name
                    # find all entities that have this option name (partial match)
                    devices = registry.refresh()
                    targets = []
                    q = name.casefold()
                    for d in devices:
                        sc = controller.list_dynamic_scenes(d.device_id)
                        for s in sc:
                            if s['instance'] != instance:
                                continue
                            for opt in (s.get('options') or []):
                                if (opt.get('name') or '').casefold().find(q) != -1:
                                    targets.append((d, s['instance'], opt))
                    if not targets:
                        print(f"No entities found exposing instance {instance!r} with option matching {name!r}.")
                        raise SystemExit(1)

                    # invoke in parallel
                    import concurrent.futures
                    def invoke_target(t):
                        d, inst, opt = t
                        try:
                            data, latency, status = controller.activate_dynamic_scene(d.device_id, inst, opt.get('value'))
                            return (d.name, inst, opt.get('name'), status, latency, None)
                        except Exception as exc:
                            return (d.name, inst, opt.get('name'), None, None, str(exc))

                    results = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(targets))) as ex:
                        futures = [ex.submit(invoke_target, t) for t in targets]
                        for f in concurrent.futures.as_completed(futures):
                            results.append(f.result())

                    # print concise results
                    for r in results:
                        name_ent, inst, opt_name, status, latency, err = r
                        if err:
                            print(f"{name_ent:24} {inst:12} {opt_name!r:20} ERROR: {err}")
                        else:
                            print(f"{name_ent:24} {inst:12} {opt_name!r:20} HTTP {status} {latency:.1f} ms")
                else:
                    # concise by default; use --verbose for full parameters
                    import json
                    print(f"Dynamic scene instances for {args.device}:")
                    for s in scenes:
                        print(f"  {s['instance']}")
                        opts = s.get('options') or []
                        if opts:
                            for opt in opts:
                                name = opt.get('name') or ''
                                val = opt.get('value')
                                print(f"    - {name} ({val})")
                        else:
                            if args.verbose:
                                if isinstance(s.get('parameters'), dict):
                                    print("    parameters:")
                                    for line in json.dumps(s['parameters'], indent=2).splitlines():
                                        print(f"      {line}")
                                else:
                                    print(f"    {s.get('parameters')}")
                            else:
                                print("    (no explicit options)")

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
