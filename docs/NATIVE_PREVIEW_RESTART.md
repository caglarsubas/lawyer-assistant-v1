# Interrupted listener restart and fresh authorization

This additive, opt-in campaign preserves the previous mount/listener report and
all of its source pins. It reuses the unchanged isolation controller with a
separately frozen 25-case plan. CI validates the evidence offline; it does not
start Docker, a listener, a provider request or a private case analysis.

Run `python scripts/qualify_native_preview_restart.py --base-image IMAGE
--output NEW_REPORT.json` against an already loaded public dependency image.
The controller resolves the immutable image ID, admits only bounded tracked
public source, and uses fresh labelled volumes. Preparation privileges never
reach runtime. Runtime has read-only source/package/root filesystems, no added
capabilities, no egress, no host mounts or published ports, and unchanged resource
bounds. Actual Docker posture is inspected before either process starts.

Seven separate worker processes exercise the same fixture stores and exact
prepared handoff. Three receive actual SIGKILL: while idle, after real reviewer
admission and receipt of a partial HTTP body, and after a completed observation.
Each exit must be -9, the listener must close, and the interrupted partial request
must release no response. Checkpoints use private inherited IPC; no fault route
or production hook is introduced. Instrumentation calls the original authority
and receive functions without replacing their decisions or bounds.

After restart, real cookie, current-session, role, Origin and CSRF checks run
again. Missing credentials, a revoked cookie, and an old CSRF token paired with
a new cookie are rejected. An explicitly created replacement fixture session
must bootstrap its own token. The exact handoff, source, provenance, preparation
time and expiry stay unchanged. Independent checksum entry is required again:
missing and incorrect entries fail, while an explicit matching entry yields a
fresh read-only observation. Startup performs no HTTP request, request replay,
comparison, history repair or authority renewal.

Expired handoffs, a changed trusted pin and a revoked preparer are rejected
before listener release. All six stores—two input/candidate stores and four
encrypted histories—retain exact bytes and file metadata after every request,
interruption and restart. Only the invented account database changes, for the
explicit reviewer-session replacement and preparer revocation. All owned
containers, volumes and generated image tags are removed; no global prune runs.

The controller retains its invented fixture in memory and forks workers after
disposing parent connections. Each worker creates a fresh SQLAlchemy connection
pool. This qualifies listener-process restart, not cold descriptor reload,
controller loss, host reboot, joint account-store rollback, real operator
approval, key custody, external checksum provenance, TLS/DNS/proxies, deployment
or legal correctness. The existing five-minute handoff lifetime is unchanged.

The first native candidate passes 25 outcomes, 15 real HTTP requests, three
SIGKILL exits and seven distinct workers. Its 745 source hashes and original
report hash bind the evidence. Twenty-nine cheap offline contracts enforce the
closed inventory, strict counters, preservation flags, isolation reuse and
scope limits. The owner's focused-analysis-v3 review remains pending.

Next: cold descriptor reconstruction and fail-closed controller-loss recovery
using independently retained fixture bindings, without automatic trust renewal.
