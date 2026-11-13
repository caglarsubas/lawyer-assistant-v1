# Delivered backend workflows: API acceptance

Run on 2026-11-13 at 04:07 UTC against application revision
`d9ff2b16cc91726ffa4fb2f44dc45d18f53aff4c`. **Seven journeys passed and
one acceptance check failed.** The failure is captured as a strict expected
failure and is excluded from the passing count. Ruff passed for the suite.

[Executable scenarios](../../tests/uat/test_delivered_workflows.py) ·
[Sanitized run receipt](backend-uat-results.json)

## Setup and limits

The suite ran on macOS with Python 3.12.11, pytest 9.1.1, two xdist workers,
FastAPI TestClient and a disposable SQLite database plus encrypted file storage
per case. Independent cookie jars held independent synthetic accounts; the
primary client alone managed application startup/shutdown. The app exercised
its real HTTP handlers, local authorization and database transactions, export
renderers, and actual demo extraction subprocess for PDF, DOCX, TXT and CSV.
The suite dropped inherited product settings, disabled dotenv loading, and
blocked IPv4/IPv6 socket connections in its test process. It used no installed
application database, private case material, real provider credentials or
external service. The analysis proposal path used **UAT-DETERMINISTIC-FIXTURE**
with two programmed outcomes; scanner and worker outages were simulated at the
application boundary. TestClient is API UAT; it provides no browser, real
PostgreSQL, deployed service or legal acceptance evidence.

## Results and requirement coverage

| Check | Result | Verified behavior and negative result |
| --- | --- | --- |
| **BAUT-01** Account, password and sessions | Pass | Wrong login returns 401. Incorrect current password is rejected without echo and leaves sibling session usable. Wrong origin and missing CSRF return 403. A valid change expires current and sibling sessions, leaves the other account signed in, requires exact whitespace-preserving new password, and preserves original bytes. Replayed logout cookie returns 401. |
| **BAUT-02** Customer, workspace, file, comments and scoped assistant | Pass | Many-to-many tags deduplicate and filter by OR; relevant date filters combine with customer and include both equal endpoints. Reversed date returns 422. Comments keep author, time and append order, store encrypted, and do not create facts. Details-only gives zero visible case count. Explicit all-cases grant allows linked source download and scoped monthly summary, excludes the B-only case, and produces an access explanation. Stale retag returns 409. Removing the qualifying link revokes session (401), and after sign-in the old case/comments/source return 404. |
| **BAUT-03** Intake, source preservation and fact roles | Pass | DOCX interleaves body paragraphs and table row; PDF distinguishes two pages; TXT retains Turkish text; CSV identifies each row. Verified each original byte for byte, encrypted on disk, with document and passage SHA-256 and exact location. Foreign workspace aliases return 404. Empty file returns 413, fake PDF and unsupported extension 415. Bad UTF-8 keeps exact original with failed extraction and zero passages. Uncited documented facts, foreign passages and failed-document IDs return 422. Allegation stays uncited; correction to disputed preserves documented revision and evidence link. |
| **BAUT-04** Exact analysis, bounded suggestion, version review and export | Pass | Rejects wrong source hash (409); dry run creates no draft. Saves actual selected Unicode range and matching hashes. Another same-firm user without case scope and a wrong-workspace route cannot read review/export. A separate reviewer records overall rationale and a distinct evidence-linked finding; blank rationale is rejected (422), bad content pin is rejected (409), and exact replay keeps one receipt. Unconfigured budget preview cannot start. One-unit overflow is rejected (422) with zero jobs; exact limit starts, old budget pin returns 409. Fixture fails with a safe typed code, then a separate retry succeeds without rewriting the original. The model boundary receives only the selected finding and exact quote, not the overall rationale, excluded finding or reviewer name. Explicit adoption creates a new unreviewed version; replay cannot readopt (409). Separate review projects conditional private review only. DOCX/PDF preserve quotations/locators, original rationale/version and hashes where checked; prior version remains withheld and both histories are retained. Fact correction makes the reviewed version stale, blocks acceptance (409), and withholds assessment on export without destroying history or originals. |
| **BAUT-05** Human supervision, revision and recipient isolation | Pass | Istanbul local deadline converts to the prior UTC date; personal overdue queue is scoped. Unassigned account cannot be added (422). Separate accounts submit independent opinions; cannot read one another's text or self-review (403). Supervisor requests revision and accepts only the new submission; old submission pin returns 409. Both author and reviewer histories remain. Removing an assignee expires the session, removes prior work access after sign-in (404), and leaves independent case access intact. |
| **BAUT-06** Extractive research and preservation | Pass | Queued extractive research produces source-bound claims and a corpus-qualification gap. General approval is blocked (409); outsider reads/exports return 404. Legal hold blocks archive/purge; release permits reversible archive, hides original and product, and leaves no physical erasure claim. Wrong restore revision returns 409; exact restore recovers identical source bytes and claim/evidence inventory. |
| **BAUT-07** No corpus, scanner or extraction worker | Pass | Catalog mode distinguishes unreviewed schema from legal data; unconfigured corpus is `not_loaded` with unknown total. Unauthorized coverage request (401), invalid date and non-allowlisted tool (422) fail closed. Missing scanner/worker and simulated scanner outage return 503; simulated malware returns 422 and does not call extraction. Simulated worker failure retains a failed, unreadable intake receipt with encrypted original, without reflecting internal diagnostics. Existing original remains accessible during intake failure. |
| **BAUT-08** Damaged encrypted private original | **Known failure; open** | A missing original or validly encrypted wrong bytes returns 409 as intended. Invalid authenticated ciphertext instead returns bare 500 `Internal Server Error`; the same request with ASGI exceptions enabled raises `cryptography.fernet.InvalidToken`. No source bytes appeared in the response. |

## BAUT-08: damaged originals need a controlled recovery response

The private original download handler checks file existence, decrypts, and
checks the document digest. The [decrypt call](../../backend/app/main.py#L685)
does not handle authentication failure. A document owner with normal access
sees a generic error for damaged ciphertext, rather than the controlled conflict
provided for the neighboring integrity failures. This blocks acceptance of the
private-original corruption recovery behavior; it does not demonstrate a
disclosure or a broader data loss.

To reproduce using only synthetic storage: upload a TXT original and verify
its bytes through `GET /api/v1/matters/{matter}/documents/{document}/original`.
In the disposable vault, replace the first byte of that document's encrypted
blob with `!`, then repeat the authenticated GET. Expect a controlled,
sanitized HTTP 409; observe generic 500. The test restores fixture ciphertext
in `finally`. Its strict expected failure matches only the verified 500 plus
`InvalidToken`; a different error fails normally, and a correct 409 produces
an XPASS requiring removal of the marker. Handle ciphertext verification
failure at the download boundary and verify recovery before closing this item.
The audit does not modify the application handler.

## Gates this run did not qualify

- **W01–W03:** Exercises actual APIs for creating accounts, explicit access,
  revocation and independent opinions. Custom-role matrix, cross-firm
  misconfiguration, migrated live data, active PostgreSQL races, suspended
  browser/session clearing, every task/deadline type and customer acceptance
  remain separate. Only the relevant-date portfolio field and monthly assistant
  summary were exercised here; creation/update date edge cases and daily/weekly
  summaries were not repeated.
- **Private preparation and R05A:** Exercises four intake formats, comments,
  document/fact provenance, fallback research, private analysis and review,
  bounded selected-finding suggestion, adoption, export and staleness.
  OCR/legacy/other formats, every advanced scenario/contradiction path, true
  provider transport or model quality, additional repair pass, independent
  public-authority review and registered comparison/cohort workflows were not
  rerun. Simulated readiness does not qualify scanner signatures, EICAR handling
  on the installed stack, extractor isolation or five-job capacity.
- **R01–R05:** Offline catalog/no-corpus behavior and extractive grounding are
  checked. Source rights, exact approved public releases, versioned historical
  authority or precedent, signed graph serving, real retrieval and corpus
  completeness still need their distinct evidence.
- **R05B–R08:** No remote BYOK, legal/domain quality, workload, fresh target-host
  deployment, or lawyer pilot was exercised. The audit does not accept those gates
  or alter prior implementation evidence.

Run from the repository root with the backend development dependencies installed:

```sh
PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m pytest \
  -c backend/pyproject.toml tests/uat/test_delivered_workflows.py -n 2 -q -rx --tb=short
backend/.venv/bin/ruff check --config backend/pyproject.toml tests/uat/test_delivered_workflows.py
```

The two-worker run took **6.58 s** locally. Both workers emitted the same
Starlette TestClient/httpx deprecation warning. This timing screens local cost;
hosted CI placement and available reserve require a separate measurement.
