if (!$('progress-change')) $('status-strip').insertAdjacentHTML('afterend','<section id="progress-change" class="progress-change" aria-labelledby="progress-title"></section>');
let roadmapProgressAxis='engineering';
const progressNumber=value=>value===null||value===undefined?'—':String(value);
function progressHTML(){
 const engineering=roadmapProgressAxis==='engineering';
 const p=engineering?D.delivery?.progress:D.progress;
 const tabs=`<div class="progress-view-switch" role="group" aria-label="Progress view"><button data-progress-axis="engineering" aria-pressed="${engineering}">Engineering subtasks</button><button data-progress-axis="readiness" aria-pressed="${!engineering}">Milestone readiness</button></div>`;
 if(!p)return tabs+'<h2 id="progress-title">Engineering receipts not yet collected</h2>';
 const before=engineering?p.before:p.before.counts,after=engineering?p.after:p.after.counts;
 const groups=engineering?[['done','Completed · merged PRs'],['open','Open PRs'],['blocked_waiting','Blocked PRs']]:[['done','Done checklist items'],['open','Open checklist items'],['blocked_waiting','Blocked / waiting items'],['deferred','Deferred items']];
 const total=engineering?Object.values(after).reduce((n,v)=>n+(v||0),0):p.after.total;
 const verified=engineering?p.verified:p.current_merge_verified;
 const label=p.baseline_pr?'PR #'+p.baseline_pr:'unrecorded baseline';
 const current=verified?'PR #'+p.current_pr+' merged':'Current work · merge pending';
 const percent=count=>total?(100*count/total).toFixed(1)+'%':'—';
 let summary='';
 if(!engineering&&D.readiness){const r=D.readiness;summary=`<div class="readiness-totals" aria-label="Declared milestone readiness">${[['ready','Ready'],['partial','Partial'],['waiting','Waiting'],['planned','Planned']].map(([key,name])=>`<span><strong>${r.counts[key]}</strong> ${name}</span>`).join('')}<span>${r.total} workstreams</span></div>`;}
 const note=engineering?'One record per repository PR: merged commit verified in this source, open PR, or explicitly blocked PR. Unstarted roadmap work is tracked in readiness. These shares describe registered PRs, not total product completion.':'The table below counts all '+total+' scoped checklist items inside '+(D.readiness?.total||14)+' workstreams. Open combines in-progress and planned items; waiting includes reviews and dependent gates. These are separate from the workstream readiness totals above.';
 const change=engineering?`${p.newly_completed.length} engineering subtask(s) completed since the baseline.`:`${p.changed.length} checklist status transitions · ${p.added.length} added · ${p.removed.length} removed. ${p.changed.length===0?'The parent checklist states remain unchanged.':''}`;
 return `${tabs}<div class="progress-head"><h2 id="progress-title">${engineering?'Engineering delivery':'Overall milestone readiness'} since ${esc(label)}</h2><span>${esc(current)}</span></div>${summary}<p class="note">${note}</p><div class="progress-table-wrap"><table><thead><tr><th scope="col">${engineering?'Engineering PR status':'Checklist status'}</th><th scope="col">Before</th><th scope="col">Now</th><th scope="col">Change</th><th scope="col">Share of this scope</th></tr></thead><tbody>${groups.map(([key,name])=>`<tr><th scope="row">${name}</th><td>${progressNumber(before[key])}</td><td><strong>${progressNumber(after[key])}</strong></td><td>${p.delta[key]>0?'+':''}${progressNumber(p.delta[key])}</td><td>${percent(after[key])}</td></tr>`).join('')}</tbody></table></div><p class="note">${esc(change)} ${engineering&&p.baseline_scope==='historical_merged_only'?'Historical open/blocked PR counts were not sampled and are shown as unknown.':''} Percentages are rounded.</p><button class="text-button" data-view="${engineering?'engineering':'milestones'}">${engineering?'Inspect completed subtasks':'Inspect readiness gates'} →</button>`;
}
function renderProgress(){ $('progress-change').innerHTML=progressHTML(); }
document.addEventListener('click',event=>{const b=event.target.closest('button[data-progress-axis]');if(b){roadmapProgressAxis=b.dataset.progressAxis;renderProgress();}});
renderProgress();
