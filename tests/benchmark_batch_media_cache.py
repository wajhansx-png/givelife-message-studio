"""Compare previous per-recipient materialization with disk reuse. Fake storage only.

Measures preparation, not WhatsApp delivery or uploads. Run from the repository:
  PYTHONPATH=tests:. python tests/benchmark_batch_media_cache.py
"""

import argparse
import base64
import json
from pathlib import Path
import tempfile
import time

import batch_media
from test_batch_media_cache import IDENT, Store


def previous_load(store, ident, folder):
    # The previous implementation read and decoded the full private blob and
    # rewrote the same file on every recipient, even if it already existed.
    row = store.get("batch_media_" + ident)
    path = Path(folder) / ("bulk-" + ident + batch_media.TYPES[row["mime"]][0])
    path.write_bytes(base64.b64decode(row["data"], validate=True))
    return path, row["mime"]


def measure(load, data, count, delay):
    store = Store(data=data, delay=delay)
    with tempfile.TemporaryDirectory() as folder:
        started = time.perf_counter()
        for _ in range(count):
            path, _ = load(store, IDENT, folder)
        elapsed = time.perf_counter() - started
        assert path.read_bytes() == data
    return {
        "seconds": round(elapsed, 5),
        "private_blob_reads": store.calls,
        "base64_bytes_fetched": store.calls * len(store.rows[IDENT]["data"]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mb", type=int, default=14)
    parser.add_argument("--recipients", type=int, default=20)
    parser.add_argument("--db-delay-ms", type=int, default=20)
    args = parser.parse_args()
    data = b"%PDF-1.7\n" + b"x" * (args.size_mb * 1_000_000)
    baseline = measure(previous_load, data, args.recipients, args.db_delay_ms / 1000)
    cached = measure(batch_media.load, data, args.recipients, args.db_delay_ms / 1000)
    print(
        json.dumps(
            {
                "scope": "attachment preparation only; no network or WhatsApp messages",
                "raw_bytes": len(data),
                "recipients": args.recipients,
                "fake_db_delay_ms": args.db_delay_ms,
                "previous": baseline,
                "cached": cached,
                "preparation_speedup": round(
                    baseline["seconds"] / max(cached["seconds"], 0.00001), 2
                ),
            },
            indent=2,
        )
    )
