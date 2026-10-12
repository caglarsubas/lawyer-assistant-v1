# Mixed Graph A/B preparation snapshots

`locked_mixed_snapshot` captures all selected current structural-law and decision-review dependencies in **one no-write transaction**. It is a prerequisite for complete release assembly, not a public graph, corpus-completeness declaration, component grant or national serving authorization. No HTTP or agent query/mutation interface is added.

The closed `legal-mixed-graph-selection-v1` request contains one existing structural source-set selection (2–8 sources) and 1–8 existing signed Graph B selections. Each decision selection retains its exact two decision sources, institutional register, independent reviewer, review/equivalence revisions and source/mapping/identity pins. Duplicate contexts, mixed source-family assignments and a source used as both decision and register are rejected. A shared register across decision contexts is supported.

One active administrator/curator must own every selected source review in the same firm. Each Graph B reviewer must remain active, independent and appointed; current signatures, ontology, source originals and all six source uses are reconstructed by the existing family-specific validators. Accepted structural mapping/review projections do not establish independent national legal approval.

The complete lock order is:

1. Every operator/reviewer account in ascending identifier order.
2. Every source in ascending identifier order, then its required source/mapping/identity heads.
3. Every equivalence and signed-review context in ascending identifier order.
4. Every canonical identity reservation in ascending identifier order.

Family reconstruction reuses this exact session and lock mode. No nested sessions or lock upgrades are permitted. Shared inspection readers can coexist; preparation defaults to exclusive locks. PostgreSQL protects dependency rows through the caller's bounded work and exit reconstruction. Explicit SQLite demo storage only performs optimistic revalidation. Existing bounded query and lock timeouts remain active.

Distinct source artifacts are bounded to 64 MiB, retained private projections to 32 MiB, structural mappings to 400, and decision contexts to eight. No partial snapshot is returned on a failure. The result reports its consistency mode, firm confidentiality and `publication_eligible: false`. Both source-family outputs retain their original compiler contracts, supporting passages, unknown dates and exact histories. Caller mutation, source/review/key/account changes or expired appointment withhold dependent output; every use must reconstruct afresh.

Use only through trusted local workflows with `readonly_store(settings)`. Keep the result in private memory or a separately encrypted private packet. Do not expose selected public-authority identifiers, private review histories, appointment data or reviewer accounts in shared graph files or matter-independent caches. If context exit raises, discard the entire dependent output.

Engineering checks cover multiple independently signed decision contexts with a shared register, reversed selection order, source-specific revocation, exact compiler input compatibility, no-write/single-connection operation, late changes and aggregate limits. Real PostgreSQL checks hold five mixed readers, observe blocked writers for both source families and reject the next use after a later decision component's rights change. Fresh authentication and real handlers remain active; no legal or permission verdict is cached.

The next gate is deterministic assembly preserving the declared retained base and every selected component, current conjunctive component/audience grants, independent review of final public bytes and a separate full-release serving authorization. This helper cannot replace those gates or fall back to an earlier valid component after another fails. Actual legal/editor vetting, nationwide ontology/corpus coverage, production key custody, deployment and held-out pilot qualification remain open.
