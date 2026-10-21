# Confidential runtime operations

Never print `.env`, mounted secret files, resolved Compose configuration, raw
container inspection, database connection strings, or private runtime receipts.
Do not use `cat`, `sed`, broad search output or exception dumps on those inputs.
Process necessary secret material only in memory or owner-only private files.

Use `scripts/runtime_diagnostics.py` for runtime reports. Its allowlisted output
contains service names, health and posture flags, never configuration values.
Use `docker compose config --quiet` for configuration validation. Pass secrets by
protected file or standard input, never command arguments, shell tracing or logs.
New secret values must never enter Git, PR text, roadmap data or screenshots.
