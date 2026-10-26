navs.splice(1,0,['backlog','Work backlog',D.backlog.total],['engineering','Engineering PR deliveries',D.delivery?.records.length||0]);
const readinessNav=navs.find(row=>row[0]==='milestones');if(readinessNav)readinessNav[1]='Milestone readiness';
meta.engineering=['Engineering PR deliveries','Evidence-linked repository deliveries. A merged PR completes its scoped change; parent readiness gates stay independent.'];
meta.backlog=['Work backlog','All unfinished checklist work, including items that have no PR yet. Open work, waiting reviews and deferred scope remain visible.'];
meta.milestones=['Overall milestone readiness',`Declared status of ${D.readiness?.total||D.milestones.length} workstreams, with the remaining evidence, accountable roles and ${D.items.length} scoped checklist items.`];
labels.done='Done · checklist item';
const doneChecklistGroup=distributionGroups.find(group=>group.status==='done');if(doneChecklistGroup)doneChecklistGroup.label='Done · checklist items';
const originalChecklistDistribution=statusDistributionHTML;statusDistributionHTML=function(){return originalChecklistDistribution().replaceAll('Item status distribution','Checklist item status distribution');};
const originalMilestoneRow=milestoneHTML;milestoneHTML=function(m){return originalMilestoneRow(m).replace('scoped engineering items done','checklist items done');};
const originalRoadmapRender=render,originalRoadmapOverview=overview,originalStatusOptions=$('status').innerHTML.replace('Done · engineering','Done checklist items');
function deliverySummaryCards(){
 const e=D.delivery?.progress?.after,r=D.readiness;if(!e||!r)return '';
 return `<section class="delivery-overview" aria-label="Separate progress views"><button class="delivery-view-card" data-view="engineering"><span class="label">Engineering delivery</span><strong>${e.done} merged PRs</strong><span>${e.open} open PRs · ${e.blocked_waiting} explicitly blocked</span><span class="text-button">Inspect merged work →</span></button><button class="delivery-view-card" data-view="milestones"><span class="label">Overall milestone readiness</span><strong>${r.counts.ready} / ${r.total} workstreams ready</strong><span>${r.counts.partial} partial · ${r.counts.waiting} waiting · ${r.counts.planned} planned</span><span class="text-button">Inspect remaining gates →</span></button></section>`;
}
overview=function(){return backlogLinkHTML()+deliverySummaryCards()+originalRoadmapOverview();};
function engineeringHTML(){
 const all=D.delivery?.records||[];
 const exact=state.q.trim().match(/^(?:PR\s*#?\s*|#)?(\d+)$/i);
 const matches=row=>exact?row.number===Number(exact[1]):textMatch({title:row.title,references:row.referenced_items},state.q);
 const rows=all.filter(row=>matches(row)&&statusMatch(row)&&(state.milestone==='all'||row.referenced_items.some(id=>D.items.find(item=>item.id===id)?.milestone===state.milestone)));
 $('result-count').textContent=`${rows.length} / ${all.length} engineering PR records · newest first · merged work and product readiness are separate`;
 return `${backlogLinkHTML()}<div class="callout"><strong>Completed work stays visible inside partial milestones.</strong><p>One record per repository PR. Completed means GitHub records a merge and its commit belongs to this source history. Open and explicitly blocked PRs are shown separately. Closed PRs without a merge are excluded. This is a delivery inventory; unstarted roadmap work remains in the work backlog.</p></div>${rows.map(row=>{
  const parents=row.referenced_items.map(id=>D.items.find(item=>item.id===id)).filter(Boolean);
  return `<details class="engineering-row"><summary><span class="row-id">#${row.number}</span><span class="row-title">${esc(row.title)}<span class="row-sub">${row.merged_at?esc(row.merged_at.slice(0,10))+' · merged delivery':'Awaiting merge'}</span></span>${badge(row.status,row.status==='done'?'Merged':row.status==='waiting'?'Blocked · label':'Open')}${chevron}</summary><div class="row-detail"><div class="detail-columns"><div><span class="label">Delivery evidence</span><p>${source(row.url,'Pull request #'+row.number+' ↗')}</p>${row.merge_commit?`<p>${source('https://github.com/caglarsubas/lawyer-assistant-v1/commit/'+row.merge_commit,'Exact merged source '+row.merge_commit.slice(0,12)+' ↗')}</p>`:'<p>Pending work is not counted as completed.</p>'}</div><div><span class="label">Checklist references</span><p>${parents.length?parents.map(item=>`<button class="dep" data-item="${esc(item.id)}">${esc(item.id+' · '+item.title)}</button>`).join(''):'No parent reference curated.'}</p><p class="note">References come from the curated delivery notes. They do not close the parent or establish legal, runtime or customer acceptance.</p></div></div></div></details>`;
 }).join('')||empty()}`;
}
function milestoneReadinessHTML(){
 const matches=m=>state.status==='all'||(state.status==='remaining'?m.status!=='done':m.status===(state.status==='in_progress'?'partial':state.status));
 const rows=D.milestones.filter(m=>matches(m)&&(state.milestone==='all'||state.milestone===m.id)&&(state.lane==='all'||state.lane===m.lane)&&(textMatch({id:m.id,title:m.title,owner:m.owner,remaining:m.remaining},state.q)||D.items.some(item=>item.milestone===m.id&&textMatch({id:item.id,title:item.title},state.q))));
 $('result-count').textContent=`${rows.length} / ${D.milestones.length} workstreams · filtered by declared readiness`;
 return `<div class="callout"><strong>${D.readiness?.counts.ready||0} of ${D.readiness?.total||D.milestones.length} workstreams are declared ready.</strong><p>Completed engineering subtasks remain visible in their own view. This view retains parent statuses, remaining requirements and review gates. The status filter applies to workstream readiness.</p><button class="text-button" data-view="engineering">See completed engineering →</button></div><div class="row-head"><span>ID</span><span>Workstream / accountable roles</span><span>Readiness</span><span>Sequence</span><span></span></div>${rows.map(milestoneHTML).join('')||empty()}`;
}
function backlogLinkHTML(){
 const b=D.backlog;
 return `<div class="callout backlog-link"><strong>${b.total} unfinished checklist items remain.</strong><p>${b.counts.open} open · ${b.counts.waiting} waiting · ${b.counts.deferred} deferred. The PR list shows only work with a registered pull request.${state.q?` Active PR search: “${esc(state.q)}”.`:''}</p><button class="text-button" data-view="backlog">Open the full work backlog →</button></div>`;
}
function backlogHTML(){
 const b=D.backlog,ids=new Set(b.ids),all=D.items.filter(item=>ids.has(item.id));
 const matchStatus=item=>state.status==='all'||(state.status==='remaining'?['in_progress','planned'].includes(item.status):item.status===state.status);
 const rows=all.filter(item=>matchStatus(item)&&(state.milestone==='all'||item.milestone===state.milestone)&&(state.lane==='all'||item.lane===state.lane)&&textMatch(item,state.q));
 $('result-count').textContent=`${rows.length} / ${b.total} unfinished items · ${b.catalog_total} checklist items in total`;
 const summary=`<div class="backlog-counts" aria-label="Full backlog status counts"><button data-backlog-status="remaining"><strong>${b.counts.open}</strong> Open work</button><button data-backlog-status="waiting"><strong>${b.counts.waiting}</strong> Waiting</button><button data-backlog-status="deferred"><strong>${b.counts.deferred}</strong> Deferred</button></div><p class="note">Counts describe the full backlog. Open includes work in progress and not yet started. Waiting includes reviews and dependent gates; it does not mean every item is externally blocked. Expand an item for its next action, required owner and dependencies. No PR is required for an item to appear here.</p>`;
 const groups=[['Open work',['in_progress','planned']],['Waiting for inputs, review or dependent gates',['waiting']],['Deferred scope',['deferred']]];
 return summary+(rows.length?groups.map(([title,statuses])=>{
  const group=rows.filter(item=>statuses.includes(item.status));
  return group.length?`<div class="group-heading"><h3>${title}</h3><span>${group.length} matching items</span></div><div class="item-list">${group.map(taskHTML).join('')}</div>`:'';
 }).join(''):`<div class="empty"><h3>No unfinished items match these filters.</h3><p>The full backlog contains ${b.total} unfinished checklist items.</p><button class="quiet" data-view="backlog">Show full backlog</button></div>`);
}
document.addEventListener('click',event=>{const button=event.target.closest('button[data-backlog-status]');if(button){navigate('backlog',{status:button.dataset.backlogStatus});$('main').focus({preventScroll:true});}});
render=function(){
 if(state.view==='backlog'&&!['all','remaining','in_progress','waiting','planned','deferred'].includes(state.status))state.status='all';
 if(state.view==='engineering'&&!['all','remaining','done','in_progress','waiting'].includes(state.status))state.status='all';
 $('status').innerHTML=state.view==='engineering'?'<option value="all">All PR states</option><option value="remaining">All unfinished PRs</option><option value="done">Completed / merged</option><option value="in_progress">Open PRs</option><option value="waiting">Explicitly blocked PRs</option>':originalStatusOptions;
 if(state.view==='milestones')$('status').innerHTML='<option value="all">All readiness states</option><option value="remaining">All unfinished workstreams</option><option value="done">Ready</option><option value="in_progress">Partial</option><option value="waiting">Waiting</option><option value="planned">Planned</option>';
 if(state.view==='backlog')$('status').innerHTML='<option value="all">All unfinished work</option><option value="remaining">Open · in progress + not started</option><option value="in_progress">In progress</option><option value="planned">Not started</option><option value="waiting">Waiting</option><option value="deferred">Deferred</option>';
 originalRoadmapRender();
 if(state.view==='checklist')$('result-count').textContent=$('result-count').textContent.replace('scoped engineering items done','checklist items done');
 if(state.view==='engineering'){
  roadmapProgressAxis='engineering';$('toolbar').hidden=false;$('status').parentElement.hidden=false;$('milestone').parentElement.hidden=false;$('lane').parentElement.hidden=true;$('expand').hidden=false;$('content').innerHTML=engineeringHTML();
 }else if(state.view==='backlog'){
  roadmapProgressAxis='readiness';$('toolbar').hidden=false;$('status').parentElement.hidden=false;$('milestone').parentElement.hidden=false;$('lane').parentElement.hidden=false;$('expand').hidden=false;$('content').innerHTML=backlogHTML();
 }else if(state.view==='milestones'){
  roadmapProgressAxis='readiness';$('content').innerHTML=milestoneReadinessHTML();
 }
 const e=D.delivery?.progress?.after,r=D.readiness;
 if(e&&r)$('status-strip').innerHTML=`<div class="stat"><strong>${e.done}</strong><span><em>Engineering PR deliveries</em>merged PR deliveries</span></div><div class="stat"><strong>${totalDone}/${D.items.length}</strong><span><em>Checklist items done</em>broader scoped items</span></div><div class="stat"><strong>${r.counts.ready}/${r.total}</strong><span><em>Workstreams ready</em>${r.counts.partial} partial · ${r.counts.waiting} waiting</span></div><div class="stat"><strong>—</strong><span><em>Legal qualification</em>not established</span></div>`;
 renderProgress();
};
readHash();render();
const trackerReadingNote=document.querySelector('footer > p');if(trackerReadingNote)trackerReadingNote.textContent='PR delivery completion means a verified merge. The work backlog contains unfinished checklist items, including work without a PR. Checklist completion closes its scoped item. Workstream readiness, legal qualification, deployment and customer acceptance are tracked independently. Waiting identifies retained inputs, reviews or dependent gates.';
