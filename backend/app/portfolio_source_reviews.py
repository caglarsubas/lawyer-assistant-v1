"""Private portfolio windows. A queue observation never authorizes source reads."""

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import aliased

from . import source_review_readiness as readiness
from .auth import authenticate, require_child, require_matter
from .content_scope import case_scope
from .db import CustomerAssignment, Record, WorkspaceCustomerLink, now
from .firm_rbac import require_permission
from .portfolio import PORTFOLIO_TIMEZONE, DateField, parse_date

RECIPE = 'private-portfolio-source-review-queue-v1'
MAX_CONTRADICTIONS = 200


def _dates(start, end):
    start, end = parse_date(start), parse_date(end)
    if start and end and start > end:
        raise HTTPException(422, 'Başlangıç tarihi bitişten sonra olamaz.')
    return start, end


def _created_filter(query, column, start, end):
    try:
        if start:
            boundary = datetime.combine(start, time.min, PORTFOLIO_TIMEZONE).astimezone(timezone.utc).isoformat()
            query = query.where(column >= boundary)
        if end:
            boundary = datetime.combine(end + timedelta(days=1), time.min, PORTFOLIO_TIMEZONE).astimezone(timezone.utc).isoformat()
            query = query.where(column < boundary)
    except (OverflowError, ValueError):
        raise HTTPException(422, 'Tarih aralığı desteklenen sınırı aşıyor.') from None
    return query


def _customers(session, user, raw):
    ids = sorted(set(part.strip() for part in raw.split(',') if part.strip()))
    if len(ids) > 100 or any(len(ident) > 64 for ident in ids):
        raise HTTPException(422, 'En fazla 100 geçerli müvekkil kimliği seçin.')
    if not ids:
        return ids
    customer, matter = aliased(Record), aliased(Record)
    assigned = exists(select(1).where(CustomerAssignment.customer_id == customer.id,
        CustomerAssignment.user_id == user.id, CustomerAssignment.firm_id == user.firm_id,
        CustomerAssignment.scope.in_(['details', 'all_cases'])))
    linked = exists(select(1).select_from(WorkspaceCustomerLink).join(matter, matter.id == WorkspaceCustomerLink.matter_id)
        .where(WorkspaceCustomerLink.customer_id == customer.id, WorkspaceCustomerLink.firm_id == user.firm_id,
            matter.kind == 'matter', matter.firm_id == user.firm_id, case_scope(matter.id, user.id, user.firm_id)))
    allowed = set(session.scalars(select(customer.id).where(customer.kind == 'customer', customer.firm_id == user.firm_id,
        customer.id.in_(ids), or_(assigned, linked))))
    if set(ids) != allowed:
        raise HTTPException(404, 'Müşteri bulunamadı')
    return ids


def _workspace_date(row, data, field, start, end):
    if not start and not end:
        return True
    raw = row.created_at if field == 'created_at' else data.get(field) or (row.created_at if field == 'updated_at' else None)
    try:
        if field == 'relevant_date':
            stamp = parse_date(raw) if raw else None
        else:
            instant = datetime.fromisoformat(raw)
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
            stamp = instant.astimezone(PORTFOLIO_TIMEZONE).date()
        return bool(stamp and (not start or stamp >= start) and (not end or stamp <= end))
    except (TypeError, ValueError, OverflowError, HTTPException):
        return False  # Unknown dates never acquire invented timestamps.


def _contradictions(store, session, matters, user):
    rows = session.scalars(select(Record).where(Record.kind == 'practice_contradiction',
        Record.firm_id == user.firm_id, Record.matter_id.in_(matters)).order_by(Record.id).limit(MAX_CONTRADICTIONS + 1)).all()
    if len(rows) > MAX_CONTRADICTIONS:
        return {ident: None for ident in matters}
    result = {ident: [] for ident in matters}
    for row in rows:
        result[row.matter_id].append((row, store.decode(row)))
    return result


def _signature(rows):
    return [(row.id, row.matter_id, row.created_at, row.revision) for row in rows]


def _route(store, session, row, user):
    from . import source_analysis_reviews as reviews

    # The caller authorized and locked this row's matter before decrypting it.
    data = store.decode(row)
    if not isinstance(data, dict):
        raise HTTPException(409, 'Kaynak bağlamının kayıt yapısı doğrulanamadı.')
    analysis_id = data.get('analysis_id')
    if (not isinstance(analysis_id, str) or not 1 <= len(analysis_id) <= 64
            or not row.id.startswith(reviews._prefix(row.matter_id, analysis_id))):
        raise HTTPException(409, 'Kaynak bağlamının analiz bağı doğrulanamadı.')
    require_child(session, analysis_id, 'practice_analysis', row.matter_id, user)
    return analysis_id


def queue(store, session, user, *, customer_ids='', date_field='created_at', date_from=None, date_to=None,
          source_date_from=None, source_date_to=None, window=10, offset=0, bucket='all'):
    from . import source_analysis_reviews as reviews

    user = require_permission(session, user, 'portfolio.read')
    require_permission(session, user, 'matter.read')
    ids = _customers(session, user, customer_ids)
    start, end = _dates(date_from, date_to)
    source_start, source_end = _dates(source_date_from, source_date_to)
    filters = {'customer_ids': ids, 'date_field': date_field, 'date_from': start.isoformat() if start else '',
        'date_to': end.isoformat() if end else '', 'source_date_from': source_start.isoformat() if source_start else '',
        'source_date_to': source_end.isoformat() if source_end else '', 'bucket': bucket}
    matter = aliased(Record)
    query = select(Record).join(matter, matter.id == Record.matter_id).where(Record.kind == reviews.KIND,
        Record.firm_id == user.firm_id, matter.kind == 'matter', matter.firm_id == user.firm_id,
        case_scope(matter.id, user.id, user.firm_id))
    if ids:
        query = query.where(exists(select(1).where(WorkspaceCustomerLink.matter_id == matter.id,
            WorkspaceCustomerLink.firm_id == user.firm_id, WorkspaceCustomerLink.customer_id.in_(ids))))
    query = _created_filter(query, Record.created_at, source_start, source_end)
    if date_field == 'created_at':
        query = _created_filter(query, matter.created_at, start, end)
    query = query.order_by(Record.created_at.desc(), Record.id).limit(window + 1).offset(offset)
    candidates = session.scalars(query).all()
    signature = _signature(candidates)
    # A consistent order prevents opposite portfolio windows from deadlocking.
    matters = {}
    for ident in sorted({row.matter_id for row in candidates[:window]}):
        current = require_matter(session, ident, user)
        session.refresh(current, with_for_update=True)
        matters[ident] = current
    session.expire_all()
    current = session.scalars(query.execution_options(populate_existing=True)).all()
    if _signature(current) != signature:
        raise HTTPException(409, 'Kuyruk işlem sırasında değişti; filtreleri koruyarak yeniden gözlemleyin.')
    data = {ident: store.decode(require_matter(session, ident, user)) for ident in matters}
    selected = [row for row in current[:window] if _workspace_date(matters[row.matter_id], data[row.matter_id], date_field, start, end)]
    contradictions = _contradictions(store, session, {row.matter_id for row in selected}, user) if selected else {}
    budget, items = [readiness.MAX_DEPENDENCIES], []
    for row in selected:
        try:
            analysis_id = _route(store, session, row, user)
            item = readiness._item(store, session, row.matter_id, analysis_id, row, user, contradictions[row.matter_id], budget)
        except HTTPException as exc:
            if exc.status_code not in {403, 404, 409}:
                raise
            analysis_id = None
            item = {'id': row.id, 'recorded_at': row.created_at, 'state': 'unavailable',
                'historical_review': {'state': 'unknown', 'id': None, 'recorded_at': None},
                'private_observation': {'state': 'unknown', 'reasons': ['private_basis_unavailable']},
                'source_verification': 'not_checked', 'legal_readiness': 'not_established'}
        title = data[row.matter_id].get('title')
        item.update(matter_id=row.matter_id, matter_title=title[:200] if isinstance(title, str) else 'Çalışma alanı', analysis_id=analysis_id)
        if bucket == 'all' or item['state'] != 'inspection_required':
            items.append(item)
    items.sort(key=lambda item: readiness.STATES[item['state']])
    for ident in matters:
        require_matter(session, ident, user)
    require_permission(session, user, 'portfolio.read')
    if _signature(session.scalars(query.execution_options(populate_existing=True)).all()) != signature:
        raise HTTPException(409, 'Kuyruk işlem sırasında değişti; yeniden gözlemleyin.')
    return reviews._bounded({'recipe': RECIPE, 'filters': filters, 'observed_at': now(), 'items': items,
        'coverage': {'scope': 'authorized_portfolio_window_only', 'scanned_count': min(len(current), window),
            'returned_count': len(items), 'locked_matter_count': len(matters), 'has_more': len(current) > window,
            'next_offset': offset + window if len(current) > window and offset + window <= 10000 else None,
            'pagination_limit_reached': len(current) > window and offset + window > 10000,
            'priority_scope': 'current_window_only', 'total_count': None, 'source_verification': 'not_checked'},
        'legal_readiness': 'not_established', 'qualification_granted': False})


def portfolio_source_review_router():
    router = APIRouter(prefix='/api/v1/work/source-reviews', tags=['private-portfolio-source-review'])

    @router.get('')
    def read(request: Request, user=Depends(authenticate), customer_ids: str = Query(default='', max_length=6500),
             date_field: DateField = 'created_at', date_from: str | None = Query(default=None, max_length=10),
             date_to: str | None = Query(default=None, max_length=10), source_date_from: str | None = Query(default=None, max_length=10),
             source_date_to: str | None = Query(default=None, max_length=10), bucket: readiness.Bucket = 'all',
             window: int = Query(default=10, ge=1, le=readiness.MAX_WINDOW), offset: int = Query(default=0, ge=0, le=10000)):
        store = request.app.state.store
        with store.session() as session:
            return queue(store, session, user, customer_ids=customer_ids, date_field=date_field, date_from=date_from, date_to=date_to,
                source_date_from=source_date_from, source_date_to=source_date_to, bucket=bucket, window=window, offset=offset)

    return router
