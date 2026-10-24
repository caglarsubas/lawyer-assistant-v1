"""Fresh invented inspection outcomes, frozen before grading or live collection."""

import json

CASES = (
    ("I2401", "good", "lookup_resolved", 7),
    ("I2402", "reference404", "lookup_rejected", 7),
    ("I2403", "metadata_mismatch", "metadata_mismatch", 7),
    ("I2404", "tag_changed", "observation_changed", 7),
    ("I2405", "binary_changed", "observation_changed", 7),
    ("I2406", "version_bad", "metadata_unmeasured", 1),
    ("I2407", "compressed", "metadata_unmeasured", 1),
    ("I2408", "timeout", "metadata_unmeasured", 1),
    ("I2409", "duplicate_selected", "metadata_unmeasured", 2),
    ("I2410", "non_gguf", "metadata_unmeasured", 7),
    ("I2411", "running_changed", "observation_changed", 7),
    ("I2412", "reference500", "metadata_unmeasured", 7),
)
SUITE_CANONICAL = json.dumps(CASES, separators=(",", ":"))
