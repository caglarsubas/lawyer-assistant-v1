# Disposable v2 selection contract

Declared before grading the fresh wording/layout/source-volume fixtures.

- Keep the frozen v2 planner, all previous suites and production unchanged.
- Use a new explicit disposable-mode marker and a separately sealed wire manifest.
  Rebuild the complete source/version plan before preparing or selecting. Preserve
  its original prompt digest and plan seal in the wire manifest.
- The v2 planner's frozen prompt contains a `B1` example while its identifiers are
  `D…`. The new wire recipe replaces that exact example with `D1`, retaining all
  other message bytes. The actual prompt digest changes; UTF-8 size and budget do
  not. Record both identities; never claim this is the unchanged planner prompt.
- Preparation is read-only and is not execution authorization. Block over-budget
  transport, forged manifests, changed unused sources, questions, limits, spans or
  plan versions before HTTP. Recheck caller context immediately before and after
  transport; discard results after a version race.
- Use the unchanged Provider's authentication, local-model/tenant-route, context,
  bounded-response, completion and no-fallback safeguards. No retries, cloud route,
  application hook or production setting can activate this experiment.
- Accept only the existing strict `bundle_ids` object with unique known `D…` IDs.
  Do not translate returned `B…` IDs, accept prose, join source parts or trim
  companions. Copy every selected bundle's exact parts, roles, source-version
  alias, nomination label, boundary flags and partial-source status.
- Report nominated versus selected source versions and omitted bundle IDs as
  confidential metadata. A valid subset or empty selection does not establish
  relevance, adverse-source completeness, abstention or legal quality.
- Freeze fresh fixtures, expected source groups, implementation and evaluator
  before their first grade. Expected groups stay outside planner and adapter.
  Retain every unavailable group, cap, omission, blocked request and fallback risk.
- Qualify transport on in-process mock HTTP and read-only, network-disabled Linux
  with public code only. Five concurrent mock selections test protocol isolation,
  not native capacity. Zero native/model or network HTTP calls are authorized by
  this experiment. A separately declared, freshly frozen native acceptance trial
  remains a later gate. Keep the private pilot and owner's v3 review pending.
