"""Payload-free measurement helpers for the opt-in application load drill."""

import math
import re


def distribution(values):
    values = sorted(values)
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("Measurements must be finite, nonnegative and nonempty")
    return {"samples": len(values), "min": round(values[0], 6), "median": round(
        (values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2, 6),
        "p95_nearest_rank": round(values[math.ceil(len(values) * .95) - 1], 6), "max": round(values[-1], 6)}


def memory_bytes(value):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(B|KiB|MiB|GiB|TiB|kB|MB|GB|TB)", value.strip())
    if not match:
        raise ValueError("Unrecognized Docker memory measurement")
    amount, unit = match.groups()
    powers = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4,
              "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    return int(float(amount) * powers[unit])


def resource_sample(row):
    used, limit = (memory_bytes(value) for value in row["MemUsage"].split("/"))
    cpu = float(row["CPUPerc"].removesuffix("%"))
    pids = int(row["PIDs"])
    if limit <= 0 or used > limit or not math.isfinite(cpu) or cpu < 0 or pids < 1:
        raise ValueError("Missing or invalid Docker resource sample")
    return {"memory_bytes": used, "memory_limit_bytes": limit, "cpu_percent": cpu, "pids": pids}


def cgroup_peaks(raw):
    """Kernel high-water marks cover short bursts that Docker sampling can miss."""
    lines = raw.splitlines()
    memory_peak, memory_limit, pid_peak, pid_limit = (int(value) for value in lines[:4])
    cpu = {key: int(value) for key, value in (line.split() for line in lines[4:])}
    if (not 0 < memory_peak <= memory_limit or not 0 < pid_peak <= pid_limit
            or not {"usage_usec", "nr_periods", "nr_throttled", "throttled_usec"} <= cpu.keys()
            or any(value < 0 for value in cpu.values())):
        raise ValueError("Incomplete or invalid cgroup v2 measurements")
    return {"memory_peak_bytes": memory_peak, "memory_limit_bytes": memory_limit,
            "pids_peak": pid_peak, "pids_limit": pid_limit, "cpu_since_container_start": cpu,
            "scope": "cgroup v2 high-water marks since startup, including small exec/probe overhead"}
