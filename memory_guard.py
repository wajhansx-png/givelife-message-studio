"""Memory guard for a small host (Render free: 512 MB). When memory runs out, the host kills the whole container at
once, so a DM batch is cut in the middle of a person. Instead, when memory gets high the launcher restarts the
container cleanly in the wait between two people (the batch carries on by itself after the restart). It also logs
how much each part uses, so a leak can be found."""

import time
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")


def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def container_memory(root=CGROUP):
    """(used, limit) in bytes, as the host counts it for out-of-memory kills (file cache that can be dropped is left
    out). (None, None) when it cannot be read."""
    current, limit = _read(root / "memory.current"), _read(root / "memory.max")  # cgroup v2
    stat_name = "inactive_file"
    if current is None:  # cgroup v1
        current = _read(root / "memory" / "memory.usage_in_bytes")
        limit = _read(root / "memory" / "memory.limit_in_bytes")
        stat_name = "total_inactive_file"
        stat = _read(root / "memory" / "memory.stat")
    else:
        stat = _read(root / "memory.stat")
    if current is None or not current.isdigit():
        return None, None
    used = int(current)
    for line in (stat or "").splitlines():
        key, _, value = line.partition(" ")
        if key == stat_name and value.isdigit():
            used = max(0, used - int(value))
    limit = int(limit) if limit and limit.isdigit() and int(limit) < 1 << 50 else None
    return used, limit


def rss(pid):
    """Resident memory of one process in bytes (0 when unknown)."""
    for line in (_read(f"/proc/{pid}/status") or "").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return 0


class Guard:
    SOFT = 0.80  # above this: restart at the next moment no person is being sent to
    HARD = 0.92  # above this: restart now (a restart still lets the current person finish first)
    MIN_UPTIME = 1800  # never restart in the first 30 minutes (no restart loop)
    REPORT = 600  # log memory every 10 minutes
    FALLBACK_LIMIT = 512 * 1024 * 1024

    def __init__(self, clock=time.monotonic, log=print):
        self.clock, self.log = clock, log
        self.started = clock()
        self.last_report = None

    def step(self, used, limit, parts, busy):
        """used/limit: container bytes; parts: {name: bytes}; busy(): True while a person is mid-send.
        Returns a reason string when the container should restart now, else None."""
        if used is None:
            used = sum(parts.values())
        limit = limit or self.FALLBACK_LIMIT
        now = self.clock()
        mb = lambda b: f"{b // (1024 * 1024)} MB"
        if self.last_report is None or now - self.last_report >= self.REPORT:
            self.last_report = now
            self.log(
                "[memory] used=%s of %s; %s"
                % (mb(used), mb(limit), " ".join(f"{k}={mb(v)}" for k, v in parts.items()))
            )
        if now - self.started < self.MIN_UPTIME or used < self.SOFT * limit:
            return None
        if used >= self.HARD * limit:
            return f"memory {mb(used)} of {mb(limit)}"
        try:
            is_busy = busy()
        except Exception:
            is_busy = True
        return None if is_busy else f"memory {mb(used)} of {mb(limit)}, between two people"
