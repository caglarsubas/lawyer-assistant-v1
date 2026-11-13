# Frontend browser UAT

On 13 November 2026, a production frontend build of `d9ff2b16cc91726ffa4fb2f44dc45d18f53aff4c` passed nine of ten Chromium scenarios. One scenario reproduced an open document selection defect. The run used Node 24.16.0, Playwright 1.64.1, and Chromium 156.0.8078.4 at 1440 × 900 and 390 × 844.

The suite serves `frontend/dist` from a temporary loopback port and exercises the bundled application in fresh browser contexts. Playwright handles the API with invented customers, workspaces, documents, drafts, and credentials. The static server rejects API requests, and the browser harness fails unexpected endpoint calls and external network requests. Results cover browser rendering, interactions, and the requests the client generates. The synthetic API controls response data and timing.

| Area | Result | Observed behavior |
| --- | --- | --- |
| Desktop workbench | Passed | All three panels collapse, reopen, and expand to the viewport. Keyboard and pointer resizing change the actual panel widths. Escape restores focus for each expanded panel. Width and collapse preferences survive reload. |
| Portfolio and assistant | Passed | Multiple customers filter with OR semantics against the fixture. The relevant-date filter includes the end day, rejects a reversed range, and resets. The weekly summary request carries the selected customers and date range. |
| Workspace files | Passed | The navigation tree opens an exact file within its workspace. The original and extracted text appear in distinct views. Upload is unavailable when intake is blocked, and a successful mock upload updates the workspace and tree. The new file can be selected explicitly. |
| Upload from a file link | Open defect | The preview returns to the previously linked file after uploading a new one. |
| Assignments and supervision | Passed | The queue combines customer/workspace-date scope with an independent overdue bucket, switches to the supervisory view, and opens the selected work record. |
| Portfolio source-review queue | Passed | Customer IDs and separate workspace/source-record dates are pinned in the request. Results show the exact context link and disclose that public sources were unchecked. A scope change cancels the delayed request and clears the result. A mismatched filter echo is rejected. |
| Review rationale and version history | Passed | Keyboard opens the two read-only examples. They leave the rationale, selected decision, criteria and review state untouched. Conditional review remains disabled with incomplete criteria. An explicit change request submits the current version, revision, digest and expected review head. Both history entries request and display their respective versions. |
| Self-service password | Passed | Missing current password blocks submission. An incorrect current password shows an error and clears all three inputs while the session stays active. The successful mock request carries the current password, both replacement fields, and CSRF token, preserving spaces and Turkish characters. The browser returns to sign-in and accepts the replacement credential with the fixture. |
| Session expiry | Passed | When session revalidation returns 401, the current document and assistant history disappear. A pending assistant reply and customer filter remain cleared after signing in again. |
| Narrow viewport and keyboard | Passed | One panel is shown at a time. Panel controls expose pressed state. The keyboard skip link moves focus to main content, and navigating from the left opens the selected page in main. No page-level horizontal overflow was observed in the queue. |

## Reproduce

Run from the repository root using Node 22 or later and a Playwright installation with its matching Chromium build. The suite resolves a standard `playwright` installation via Node. With Playwright installed separately, set `UAT_PLAYWRIGHT_ENTRY` to the absolute path of its `playwright/index.js`. For example, use a scratch directory to keep the browser tooling outside the repository.

```sh
npm ci --prefix frontend
npm run build --prefix frontend
uat_tool_dir="$(mktemp -d)"
npm install --prefix "$uat_tool_dir" --no-package-lock playwright@1.64.1
"$uat_tool_dir/node_modules/.bin/playwright" install chromium
UAT_PLAYWRIGHT_ENTRY="$uat_tool_dir/node_modules/playwright/index.js" \
  node --test --test-concurrency=1 tests/uat/browser/workbench.test.mjs
```

The upload-selection test executes the intended assertion as a Node TODO. Node exits successfully for a failing TODO. Count it as open when reading the result or its JUnit report. Browser acceptance requires all scenarios to pass, including this case.

## Open defect

1. In **Gezinme**, expand a workspace with multiple files.
2. Open a file from the tree and verify the URL includes `?tab=documents&document=…`.
3. Upload another file while viewing that file.
4. The success notice and refreshed lists include the upload, while the preview returns to the original file. Select the new file manually to inspect it.

The [document selection effect](../../frontend/src/pages/matter/DocumentsPanel.tsx#L36) runs again when the refreshed document array arrives. It reapplies the document from the URL over the [selection of the latest upload](../../frontend/src/pages/matter/DocumentsPanel.tsx#L45).

## Coverage limits

This run leaves live deployment, password storage and multi-session revocation, backend authorization and persistence, scanner/extractor operation, full source-context handoffs, provider calls, PDF/DOCX rendering, large-portfolio load, cross-browser and physical-device behavior, screen reader testing, and lawyer acceptance unverified. The review scenario exercises a fictional change request. Its historical review fixture supplies the prior conditional decision.
