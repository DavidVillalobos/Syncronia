from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
from collections import defaultdict

from .models import RequestMetric


class StatsStore:
    def __init__(self, path: str | Path = "data/stats.jsonl"):
        self.path = Path(path)

    def record(self, metric: RequestMetric) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **asdict(metric),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def summary(self, device_name: str | None = None) -> list[dict]:
        rows = self.read()
        if device_name:
            q = device_name.casefold()
            rows = [
                r for r in rows
                if q in (r.get("device_name") or "").casefold()
            ]

        grouped = defaultdict(list)
        for row in rows:
            key = row.get("device_name") or "(account/API)"
            grouped[key].append(row)

        out = []
        for key, items in sorted(grouped.items()):
            successes = [x for x in items if x.get("ok")]
            latencies = [
                float(x["latency_ms"])
                for x in successes
                if x.get("latency_ms") is not None
            ]
            online_values = [
                x.get("online")
                for x in items
                if x.get("online") is not None
            ]
            out.append({
                "device": key,
                "samples": len(items),
                "success_rate": (
                    len(successes) / len(items) * 100 if items else 0
                ),
                "avg_latency_ms": (
                    sum(latencies) / len(latencies)
                    if latencies else None
                ),
                "min_latency_ms": min(latencies) if latencies else None,
                "max_latency_ms": max(latencies) if latencies else None,
                "last_online": (
                    online_values[-1] if online_values else None
                ),
            })
        return out
