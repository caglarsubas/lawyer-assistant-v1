# Native receipt-package qualification

The opt-in campaign qualifies **Linux Docker/ext4 read-only packaging and fresh
process isolation**. It uses a public-only nine-module export of the existing
receipt adapter. The eight source modules and their semantics remain unchanged.
It does not register a product route, install a runtime, contact a provider or
read any private case, credential, review or document store.

Each frozen case runs in a fresh `-I -B` Python process. A trusted external
inspector applies its default read-only requirement **before package imports**.
The valid case imports all modules, verifies an actual `EROFS` denial and checks
disposable receipt-store/profile/key/scope pins without mutating the fixture.
Readiness leaves custody and appointments unassessed. Incorrect independent pins
must block. No application or inference-engine dependency may load.

The nine rejection cases cover a wrong manifest pin, an extra file, unsafe file
permissions, a symlink, a hardlink outside the package, a forbidden application
import with otherwise matching manifest hashes, an actually writable mount,
wrong ownership, and changed module bytes. Matching hashes cannot bypass the
dependency policy. The closed report rejects missing, duplicated, reordered or
uninspected cases, process reuse, missing kernel proof and authority inflation.

## Run on a disposable local Docker engine

Use an already loaded **public dependency image** containing the locked backend
Python environment. Only its dependency layer is reused; current public probe,
inspector and exported package sources are copied into a fresh qualification
image. The image ID and source hashes are retained. No image is pulled.

```sh
backend/.venv/bin/python scripts/qualify_receipt_stage.py \
  --base-image lawyer-assistant-api:long-page-quotes-v1 \
  --output /absolute/owner-only/new-native-report.json
```

The output must be new. Incomplete/failing runs retain an incomplete result and
exit nonzero. The harness generates fresh labelled volumes; it accepts no host
mount, existing-volume, private path or `.env` option. Preparation alone uses
root with three explicit filesystem capabilities. Runtime uses UID 10002, no
capabilities, a read-only root filesystem and stage volume, network `none`, no
published port, two CPUs, 1 GiB memory and 64 processes. Actual Docker posture is
checked before each start. Native volumes must report ext4. Only this campaign's
containers and labelled volumes are removed; no shared-resource cleanup occurs.

## Limits and next gate

The campaign performs **zero HTTP requests**. It does not supply evidence for a
native authenticated adapter/controller exchange, retained-receipt restart,
actual operator appointments, independent key custody, inference, production
installation or legal review. The existing 17 authenticated adapter tests remain
separate in-process evidence. The next slice is native loopback HTTP with real
disposable host sessions and independently pinned controller bindings.

The lightweight closed-report and safe-wiring regressions run in the existing
candidate CI group. Docker qualification remains opt-in. All 1,018 deployment
methods, ten jobs, two-worker ceilings, source pins, time limits and job/phase
reserve floors are retained. CI, merge and independent main qualification are
distinct gates. Owner review of the private analysis stays pending.
