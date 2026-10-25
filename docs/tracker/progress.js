if (!$('progress-change')) $('status-strip').insertAdjacentHTML('afterend','<section id="progress-change" class="progress-change" aria-labelledby="progress-title"></section>');

function progressHTML(){
 const p=D.progress;if(!p)return '<h2 id="progress-title">Progress comparison unavailable</h2>';
 const groups=[['done','Done · engineering'],['open','Open'],['blocked_waiting','Blocked / waiting'],['deferred','Deferred']];
 const label=p.baseline_pr?'PR #'+p.baseline_pr:'Initial snapshot';
 const current=p.current_merge_verified?'PR #'+p.current_pr+' merged':'Current work · merge pending';
 const percent=(count,total)=>total?(100*count/total).toFixed(1)+'%':'—';
 return `<div class="progress-head"><h2 id="progress-title">Progress since ${esc(label)}</h2><span>${esc(current)}</span></div><div class="progress-table-wrap"><table><thead><tr><th scope="col">Status</th><th scope="col">Before</th><th scope="col">Now</th><th scope="col">Change</th><th scope="col">Current share</th></tr></thead><tbody>${groups.map(([key,label])=>`<tr><th scope="row">${label}</th><td>${p.before.counts[key]}</td><td><strong>${p.after.counts[key]}</strong></td><td>${p.delta[key]>0?'+':''}${p.delta[key]}</td><td>${percent(p.after.counts[key],p.after.total)}</td></tr>`).join('')}</tbody></table></div><p class="note">All ${p.after.total} scoped items; previous total ${p.before.total}. Open = in progress + planned. Blocked / waiting = the catalog’s waiting status, including pending reviews and dependent gates. Deferred stays separate. Item counts do not measure effort or legal/release readiness.</p><p class="note">${p.changed.length} status transitions · ${p.added.length} added · ${p.removed.length} removed. ${p.changed.length===0&&p.added.length===0&&p.removed.length===0?'Engineering advanced within a partial item; no checklist gate was closed.':''}</p>`;
}
$('progress-change').innerHTML=progressHTML();
