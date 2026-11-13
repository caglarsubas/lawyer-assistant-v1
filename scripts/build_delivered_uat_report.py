#!/usr/bin/env python3
"""Render the retained, sanitized acceptance audit as a portable HTML report."""

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(audit, catalog):
    if audit["reviewed_source"] != catalog["reviewed_source"]:
        raise ValueError("Audit and catalog sources differ")
    esc = html.escape
    def distribution(title, values):
        total = sum(values.values())
        bars = ''.join(f'<div class="bar {esc(k)}" style="flex-grow:{v}" title="{esc(k)} {v}"></div>'
                       for k, v in values.items() if v)
        rows = ''.join(f'<li><span>{esc(k.replace("_", " "))}</span><b>{v}</b><span>{v / total:.1%}</span></li>'
                       for k, v in values.items())
        return f'<article class="metric"><h2>{esc(title)}</h2><div class="stack">{bars}</div><ul>{rows}</ul></article>'
    charts = distribution("Selected synthetic journeys", {"passed": audit["journeys"]["passed"],
                          "known_failure": audit["journeys"]["known_failures"]})
    charts += distribution("Product checklist · 93 items", audit["counts"]["checklist"])
    charts += distribution("Milestone readiness · 14", audit["counts"]["milestones"])
    findings = ''
    for f in audit["findings"]:
        findings += (f'<article class="finding" data-search="{esc(" ".join(str(v) for v in f.values()), quote=True)}">'
                     f'<p class="eyebrow">{esc(f["id"])} · {esc(f["priority"])} · {esc(f["status"])} · {esc(f["kind"])}</p>'
                     f'<h3>{esc(f["title"])}</h3><p>{esc(f["detail"])}</p><p><b>Exit:</b> {esc(f["acceptance"])}</p>'
                     f'<p class="muted">Roadmap: {esc(", ".join(f["items"]))}</p></article>')
    rows = ''
    for item in catalog["items"]:
        refs = ''.join(f'<a href="https://github.com/caglarsubas/lawyer-assistant-v1/blob/{catalog["reviewed_source"]}/{esc(p, quote=True)}">{esc(p)}</a><br>'
                       for p in item["code"] + item["tests"])
        rows += (f'<tr data-search="{esc(" ".join(str(v) for v in item.values()), quote=True)}">'
                 f'<th>{esc(item["id"])}</th><td>{esc(item["title"])}</td><td>{esc(item["status"])}</td>'
                 f'<td>{esc(item["scope"].replace("_", " "))}</td><td>{refs}</td><td>{esc(item["remaining_gate"])}</td></tr>')
    sequence = ''.join(f'<li>{esc(x)}</li>' for x in audit["next_sequence"])
    base = audit["reviewed_source"]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Türkiye Legal Assistant — delivery and UAT audit</title><style>
:root{{font-family:system-ui,sans-serif;color:#20332d;background:#f6f5ef;line-height:1.6}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1320px;margin:auto;padding:32px}}a{{color:#235b48}}h1{{font-size:clamp(28px,4vw,44px);line-height:1.2;max-width:900px}}h2{{font-size:20px}}h3{{margin:4px 0}}.eyebrow,.muted{{color:#53665d}}.eyebrow{{font-size:12px;letter-spacing:.05em}}.notice{{border-left:5px solid #a65a37;background:#f1e5d5;padding:16px 22px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:28px 0}}.metric{{background:white;border:1px solid #cdd5cb;padding:20px}}.metric h2{{margin-top:0}}.stack{{display:flex;height:15px;background:#eee;gap:2px}}.bar{{background:#bdc7b9}}.passed,.done,.ready{{background:#377760}}.known_failure,.waiting{{background:#b76142}}.open,.partial{{background:#c6a351}}.metric ul{{list-style:none;padding:0;margin-bottom:0}}.metric li{{display:grid;grid-template-columns:1fr 50px 65px;padding:6px 0;border-bottom:1px solid #eceee9}}.metric li span:last-child{{text-align:right}}nav{{display:flex;gap:20px;flex-wrap:wrap}}input{{font:inherit;padding:12px;width:min(600px,100%);border:1px solid #708273;background:white}}label{{display:block;margin-top:28px}}.finding{{padding:20px 0;border-bottom:1px solid #ced4cc}}.table-scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px;background:white}}th,td{{text-align:left;vertical-align:top;border:1px solid #d8ded5;padding:10px;min-width:100px}}td:nth-child(5){{font-size:11px;overflow-wrap:anywhere;min-width:220px}}td:last-child{{min-width:250px}}[hidden]{{display:none!important}}:focus-visible{{outline:3px solid #8d5b2c;outline-offset:3px}}footer{{margin-top:32px;padding-top:20px;border-top:1px solid #ccd4ca;font-size:13px}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}main{{padding:20px}}}}
</style></head><body><main>
<p class="eyebrow">TÜRKİYE LEGAL ASSISTANT · AUDIT {esc(audit['observed_on'])}</p>
<h1>What has shipped, what works, and what still blocks acceptance</h1>
<p>Reviewed by three GPT‑6.1‑sol agents at xhigh effort. Audit baseline <code>{base[:12]}</code>; this is a historical, source-bound assessment.</p>
<div class="notice"><strong>{esc(audit['verdict'])}</strong><p>The selected tests use synthetic cases. No client originals, private case records or review decisions were changed. Neither green CI nor an engineering completion grants legal or production approval.</p></div>
{charts}<p class="muted">The three distributions have different denominators. They are not interchangeable completion percentages. Engineering baseline: 295 merged PRs, 0 open PRs, 0 labelled blocked PRs.</p>
<nav><a href="/">Current roadmap</a><a href="#findings">Findings</a><a href="#sequence">Next delivery sequence</a><a href="#coverage">All 93 checklist mappings</a><a href="https://github.com/caglarsubas/lawyer-assistant-v1/tree/main/docs/quality">Reports and executable checks</a></nav>
<label for="filter">Filter findings and checklist by ID, status, domain or source file</label><input id="filter" type="search" placeholder="For example: F00, waiting, evidence, review"><p id="count" aria-live="polite"></p>
<section id="findings"><h2>Observed defects, blockers and planning gaps</h2>{findings}</section>
<section id="sequence"><h2>Next delivery sequence</h2><ol>{sequence}</ol></section>
<section id="coverage"><h2>Complete checklist evidence map</h2><p>Paths link to the audited commit. A code or test reference identifies scope; it does not certify the remaining gate.</p><div class="table-scroll"><table><thead><tr><th>ID</th><th>Requirement</th><th>Recorded state</th><th>Evidence scope</th><th>Code and tests</th><th>Remaining gate</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<footer>Independent main CI at the baseline: 13/13, minimum job reserve 42s, two workers per job. Current relay/scanner operation, exact installed-version parity, signed-in production UAT and owner review remain separate. Full baseline: <code>{base}</code>.</footer>
</main><script>
const filter=document.getElementById('filter'),rows=[...document.querySelectorAll('[data-search]')];
function apply(){{const q=filter.value.toLocaleLowerCase('en');let shown=0;for(const row of rows){{row.hidden=!row.dataset.search.toLocaleLowerCase('en').includes(q);if(!row.hidden)shown++;}}document.getElementById('count').textContent=shown+' of '+rows.length+' findings and checklist entries shown';}}filter.addEventListener('input',apply);apply();
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/quality/uat-report.html")
    args = parser.parse_args()
    audit = json.loads((ROOT / "docs/quality/delivered-audit.json").read_text())
    catalog = json.loads((ROOT / "docs/quality/roadmap-sanity-catalog.json").read_text())
    args.output.write_text(render(audit, catalog))
    print(json.dumps({"output": str(args.output), "checklist_items": len(catalog["items"]),
                      "findings": len(audit["findings"]), "reviewed_source": audit["reviewed_source"]}))


if __name__ == "__main__":
    main()
