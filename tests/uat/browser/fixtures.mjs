import assert from 'node:assert/strict';

export const session = {
  user: {
    id: 'uat-lawyer', name: 'Sentetik UAT Kullanıcısı', firm_id: 'uat-firm', role: 'lawyer',
    permissions: ['portfolio.read', 'matter.read'],
  },
  csrf_token: 'uat-synthetic-token', demo_mode: false,
};
export const password = 'uat-örnek-eski-parola';
export const replacement = '  uat-örnek-yeni-parola  ';
export const customers = [
  { id: 'uat-alpha', name: 'UAT Müvekkil Alfa' },
  { id: 'uat-beta', name: 'UAT Müvekkil Beta' },
  { id: 'uat-gamma', name: 'UAT Müvekkil Gama' },
];
const timestamp = '2026-10-21T12:00:00Z';
export const filename = 'uat-sentetik-dayanak.txt';
export const uploadedFilename = 'uat-yeni-belge.txt';
export const original = 'UAT özgün belge içeriği.';
export const extracted = 'UAT çıkarılan pasaj.';

function document(id, name, text, synthetic = false) {
  return {
    id, name, status: 'ready', media_type: 'text/plain', page_count: null,
    extraction_warnings: [], created_at: timestamp, synthetic,
    passages: [{ id: id + '-passage', locator: '§1', text }],
  };
}

function workspace(id, title, customerIndexes, relevant_date, documents) {
  const linked = customerIndexes.map(index => customers[index]);
  return {
    id, title, relevant_date, documents, domain: 'contracts', status: 'active',
    objective: 'Sentetik çalışma amacı', represented_party: '', stage: '',
    document_count: documents.length, created_at: timestamp, updated_at: timestamp,
    customer_ids: linked.map(customer => customer.id), customers: linked, facts: [], products: [],
  };
}

const alpha = workspace('uat-case-a', 'UAT Alfa dosyası', [0, 1], '2026-09-10', [
  document('uat-document-first', 'uat-ilk-belge.txt', 'UAT ilk pasaj.', true),
  document('uat-document-selected', filename, extracted),
]);
const beta = workspace('uat-case-b', 'UAT Beta dosyası', [1], '2026-09-24', [
  document('uat-document-beta', 'uat-beta-belgesi.txt', 'UAT Beta pasajı.', true),
]);
const gamma = workspace('uat-case-c', 'UAT Gama dosyası', [2], '2026-09-17', []);
export const workspaces = [alpha, beta, gamma];
export const matterPath = '/workspaces/' + alpha.id;
export const analysisPath = '/matters/' + alpha.id + '/analyses';
export const reviewsPath = analysisPath + '/uat-analysis/reviews';
export const version2 = 'uat-version-2';
export const version1 = 'uat-version-1';
export const version2Hash = 'a'.repeat(64);
const version1Hash = 'b'.repeat(64);
export const rationale = 'UAT: Kurgusal taslaktaki dayanak eksikliğinin açıklanmasını istiyorum.';
export const historicalNote = 'UAT: Önceki sürümün kurgusal inceleme gerekçesi.';
export const analysisTitle = 'UAT sentetik analiz taslağı';
const scope = 'conditional_private_draft_only';
const recipe = 'private-lawyer-review-v1';
const freshness = { status: 'current', reasons: [], scope: 'selected_private_dependencies_only' };
const reviewCriteria = {
  sources: 'Özgün alıntıların değerlendirildiğini belirtin.',
  reasoning: 'Koşulları ve gerekçeyi değerlendirin.',
  fact_roles: 'Olgu rollerini ve çelişkileri değerlendirin.',
  limits: 'Kapsam sınırlarını değerlendirin.',
  ai_contribution: 'Model katkısını değerlendirin.',
};

function content(version) {
  return {
    title: analysisTitle, issue: 'UAT sürüm ' + version + ' meselesi', posture: '', event_date: null,
    evidence: [], premises: [], rules: [], applications: [], alternatives: [], fact_snapshots: [],
    conclusion: {
      text: 'UAT sürüm ' + version + ' sonucu', requested_disposition: 'conditional',
      application_ids: [], alternative_ids: [], uncertainty: [], next_step: '',
    },
    checks: {
      recipe: 'private-rationale-checks-v1', scope: 'declared_structure_only', legal_approval: 'not_granted',
      effective_disposition: 'conditional', critical_count: 0, defects: [], dependency_nodes: [],
    },
    revision_comparison: {
      previous_version_id: version === 2 ? version1 : null, changed_sections: [], changed_dependency_groups: [],
      checks_no_longer_triggered: [], new_check_ids: [], scope: 'structural_changes_only',
    },
    status: 'needs_review', authorship: 'user', legal_authority: false,
  };
}

const oldReview = {
  id: 'uat-review-1', version_id: version1, sequence: 1, created_at: timestamp,
  content_sha256: version1Hash, decision: 'reviewed_conditional', reviewer_id: 'uat-historical-reviewer',
  reviewer_name: 'Sentetik önceki avukat', note: historicalNote,
  criteria: Object.keys(reviewCriteria).map(criterion => ({ criterion, outcome: 'confirmed', note: '' })),
  findings: [], scope, recipe,
};

function reviewProjection(event) {
  return { effective_state: event?.decision ?? 'unreviewed', scope, latest: event, reasons: [] };
}

function workItem(workspace, id, title, overdue) {
  return {
    id, title, overdue, description: 'UAT açıklaması: ' + title, revision: 1, kind: 'task',
    due_local: '2026-10-20T15:00', due_at: '2026-10-20T12:00:00Z', time_zone: 'Europe/Istanbul',
    status: 'open', assignee_ids: [session.user.id], matter_id: workspace.id, matter_title: workspace.title,
    viewer_id: session.user.id, request_version: 1, can_manage: false, can_review: false, can_act: false,
    responses: [],
  };
}

export const jobs = [
  workItem(alpha, 'uat-task-a', 'UAT Alfa görevi', true),
  workItem(beta, 'uat-task-b', 'UAT Beta görevi', false),
  workItem(gamma, 'uat-task-c', 'UAT Gama görevi', true),
];
export const sourceContextId = 'sac-' + 'a'.repeat(20) + '-' + 'b'.repeat(32);

function portfolio(query, workspaces) {
  const customers = query.get('customer_ids')?.split(',') || [];
  const field = query.get('date_field');
  const from = query.get('date_from');
  const to = query.get('date_to');
  assert.ok(['created_at', 'updated_at', 'relevant_date'].includes(field));
  return workspaces.filter(item => {
    const day = item[field]?.slice(0, 10);
    return (!customers.length || customers.some(id => item.customer_ids.includes(id)))
      && (!from || day >= from) && (!to || day <= to);
  });
}

function sourceQueue(params, workspaces, mismatched) {
  const filters = {
    customer_ids: params.get('customer_ids')?.split(',') || [],
    date_field: params.get('date_field'),
    date_from: params.get('date_from') || '',
    date_to: params.get('date_to') || '',
    source_date_from: params.get('source_date_from') || '',
    source_date_to: params.get('source_date_to') || '',
    bucket: params.get('bucket'),
  };
  assert.equal(params.get('offset'), '0');
  const recordedDay = timestamp.slice(0, 10);
  const match = portfolio(params, workspaces).some(item => item.id === alpha.id)
    && (!filters.source_date_from || recordedDay >= filters.source_date_from)
    && (!filters.source_date_to || recordedDay <= filters.source_date_to);
  const items = match ? [{
    id: sourceContextId, recorded_at: timestamp, state: 'inspection_required',
    matter_id: alpha.id, matter_title: alpha.title, analysis_id: 'uat-analysis',
    version_id: version2, product_id: 'uat-product', manifest_sha256: 'c'.repeat(64),
    historical_review: {
      state: 'reviewed_conditional', id: 'sar-' + 'd'.repeat(20) + '-' + 'e'.repeat(32),
      recorded_at: timestamp,
    },
    private_observation: { state: 'unchanged', reasons: [] },
    source_verification: 'not_checked', legal_readiness: 'not_established',
  }] : [];
  return {
    recipe: 'private-portfolio-source-review-queue-v1', observed_at: timestamp,
    filters: mismatched ? { ...filters, customer_ids: ['uat-other-scope'] } : filters,
    legal_readiness: 'not_established', qualification_granted: false,
    coverage: {
      scope: 'authorized_portfolio_window_only', scanned_count: 1, returned_count: items.length,
      locked_matter_count: 1, has_more: false, next_offset: null, pagination_limit_reached: false,
      priority_scope: 'current_window_only', total_count: null, source_verification: 'not_checked',
    },
    items,
  };
}

export async function fixture(context, origin, { signedIn = true } = {}) {
  const state = {
    signedIn, blocked: false, activePassword: password, calls: [], unexpected: [],
    workspaces: structuredClone(workspaces), review: null, lateGuide: null,
    lateQueue: null, mismatchedQueue: false,
  };

  function respond(call, route) {
    const { path, method, params, body, csrf } = call;
    const json = (value, status = 200) => route.fulfill({ status, json: value });
    const invalid = () => json({ detail: 'UAT: Kullanıcı adı veya parola geçersiz.' }, 401);
    if (method === 'GET' && path === '/bootstrap') return json({ version: 'uat', demo_mode: false });
    if (method === 'GET' && path === '/auth/me') return state.signedIn ? json(session) : invalid();
    if (method === 'POST' && path === '/auth/login') {
      assert.deepEqual(Object.keys(body).sort(), ['password', 'username']);
      if (body.username !== session.user.id || body.password !== state.activePassword) return invalid();
      state.signedIn = true;
      return json(session);
    }
    if (!state.signedIn) return invalid();
    if (method === 'POST') assert.equal(csrf, session.csrf_token);
    if (method === 'GET' && path === '/status') return json({
      demo_mode: false, provider: { configured: false }, graphs: {}, services: {}, limitations: [],
    });
    if (method === 'POST' && path === '/auth/password') {
      assert.deepEqual(Object.keys(body).sort(), ['confirm_password', 'current_password', 'new_password']);
      if (body.current_password !== state.activePassword) return json({ detail: 'UAT: Mevcut parola doğrulanamadı.' }, 400);
      assert.equal(body.confirm_password, body.new_password);
      state.activePassword = body.new_password;
      state.signedIn = false;
      return json({ ok: true, reauthentication_required: true });
    }
    if (method === 'GET' && path === '/customers') return json(customers);
    if (method === 'GET' && path === '/workspaces') return json(portfolio(params, state.workspaces));
    if (method === 'GET' && path === '/intake/readiness') return json({
      status: state.blocked ? 'blocked' : 'ready', issues: [], scanner: { status: 'ready' }, extractor: { status: 'ready' },
    });
    const matter = state.workspaces.find(item => path === '/workspaces/' + item.id);
    if (method === 'GET' && matter) return json(matter);
    if (method === 'GET' && path === matterPath + '/access') return json({
      direct_case_grant: true, client_all_cases_origins: [], permissions: ['matter.read'], team: [],
      supervisor: false, responsible: true,
    });
    if (method === 'POST' && path === '/matters/' + alpha.id + '/documents') {
      assert.match(route.request().headers()['content-type'], /^multipart\/form-data; boundary=/);
      assert.ok(route.request().postData().includes(uploadedFilename));
      const uploaded = document('uat-uploaded', uploadedFilename, 'UAT yeni çıkarılan pasaj.');
      state.workspaces[0].documents.push(uploaded);
      state.workspaces[0].document_count++;
      return json(uploaded, 201);
    }
    const fileRoute = /^\/matters\/([^/]+)\/documents\/([^/]+)(\/original)?$/.exec(path);
    if (method === 'GET' && fileRoute) {
      const [, matterId, documentId, suffix] = fileRoute;
      const found = state.workspaces.find(item => item.id === matterId)?.documents.find(item => item.id === documentId);
      if (!found) return json({ detail: 'UAT: Belge bulunamadı.' }, 404);
      return suffix ? route.fulfill({ contentType: 'text/plain; charset=utf-8', body: original }) : json(found);
    }
    if (method === 'POST' && path === '/assistant/respond') {
      const reply = () => json({
        mode: body.mode, answer: 'UAT özel bağlam yanıtı.', provider_used: false, sources: [],
        suggestions: [], limitations: [], period: null,
      });
      return state.lateGuide ? state.lateGuide.then(reply) : reply();
    }
    if (method === 'GET' && path === '/work') {
      const bucket = params.get('bucket');
      const view = params.get('view');
      assert.ok(['personal', 'supervisory'].includes(view));
      assert.ok(['all', 'upcoming', 'overdue', 'closed'].includes(bucket));
      const items = view === 'personal' ? jobs : jobs.slice(0, 1);
      return json({ items: items.filter(item => bucket === 'all'
        || (bucket === 'overdue' && item.overdue) || (bucket === 'upcoming' && !item.overdue)), truncated: false });
    }
    if (method === 'GET' && path === '/work/source-reviews') {
      const result = sourceQueue(params, state.workspaces, state.mismatchedQueue);
      return state.lateQueue ? state.lateQueue.then(() => json(result)) : json(result);
    }
    if (method === 'GET' && path === matterPath + '/work') return json({
      items: [jobs[0]], can_manage: false, people: [], time_zone: 'Europe/Istanbul',
    });
    if (method === 'GET' && path === matterPath + '/work/' + jobs[0].id) return json(jobs[0]);
    if (method === 'GET' && (path === '/playbooks'
      || new RegExp('^/matters/' + alpha.id + '/practice/(scenarios|contradictions|arguments|drafts|playbooks)$').test(path))) {
      return json([]);
    }
    if (method === 'GET' && path === analysisPath) return json([{
      ...content(2), id: 'uat-analysis', revision: 2, version: 2, latest_version_id: version2,
      created_at: timestamp, freshness, review: reviewProjection(state.review),
    }]);
    if (method === 'GET' && path === analysisPath + '/uat-analysis/versions') return json([2, 1].map(version => ({
      id: version === 2 ? version2 : version1, version, content: content(version),
      change_note: version === 2 ? 'UAT sentetik metin değişikliği' : '', created_at: timestamp,
      freshness, review: reviewProjection(version === 2 ? state.review : oldReview),
    })));
    if (method === 'GET' && path === reviewsPath + '/context') {
      assert.equal(params.get('version_id'), version2);
      return json({
        version_id: version2, expected_revision: 2, content_sha256: version2Hash,
        expected_review_id: state.review?.id ?? null, recipe, criteria: reviewCriteria, ai_contribution_required: false,
        current_version: true, can_record: true, can_accept: true, critical_count: 0,
        freshness, review: reviewProjection(state.review), targets: ['analysis', 'conclusion'], sources: [],
      });
    }
    if (method === 'GET' && path === reviewsPath) {
      const version = params.get('version_id');
      assert.ok([version1, version2].includes(version));
      return json(version === version1 ? [oldReview] : state.review ? [state.review] : []);
    }
    if (method === 'POST' && path === reviewsPath) {
      assert.equal(body.version_id, version2);
      assert.equal(body.expected_revision, 2);
      assert.equal(body.expected_review_id, null);
      assert.equal(body.content_sha256, version2Hash);
      assert.match(body.request_id, /^[a-f0-9]{32}$/);
      state.review = {
        id: 'uat-review-2', version_id: body.version_id, sequence: 1, created_at: timestamp,
        content_sha256: body.content_sha256, decision: body.decision, reviewer_id: session.user.id,
        reviewer_name: session.user.name, note: body.note, criteria: body.criteria, findings: body.findings,
        scope, recipe,
      };
      return json(state.review, 201);
    }
    throw new Error('Unhandled fixture endpoint');
  }

  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) {
      state.unexpected.push('External request to ' + url.origin);
      return route.abort();
    }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const method = route.request().method();
    try {
      const call = { path, method, params: url.searchParams, csrf: route.request().headers()['x-csrf-token'] };
      if (route.request().headers()['content-type'] === 'application/json') call.body = route.request().postDataJSON();
      state.calls.push(call);
      await respond(call, route);
    } catch (error) {
      state.unexpected.push(method + ' ' + path + ' ' + error.message);
      await route.abort().catch(() => {});
    }
  });
  return state;
}
