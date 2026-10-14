from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.companies.service import owned as owned_company
from app.modules.discovery.candidates import name_candidate
from app.modules.discovery.models import (
    CareerSource,
    DiscoveryCandidate,
    DiscoveryScan,
    ScanOutbox,
)
from app.modules.discovery.schemas import (
    CandidateView,
    CareerSourceView,
    ScanPage,
    ScanSelection,
    ScanSummary,
    ScanView,
)
from app.modules.extraction.service import latest_for_sources

ACTIVE = ("queued", "running", "needs_input")


def summary(scan: DiscoveryScan) -> ScanSummary:
    return ScanSummary.model_validate(scan, from_attributes=True)


async def view(db: AsyncSession, scan: DiscoveryScan) -> ScanView:
    candidates = list(
        (
            await db.scalars(
                select(DiscoveryCandidate)
                .where(DiscoveryCandidate.scan_id == scan.id)
                .order_by(DiscoveryCandidate.id)
            )
        ).all()
    )
    sources = list(
        (
            await db.scalars(
                select(CareerSource)
                .where(CareerSource.scan_id == scan.id)
                .order_by(CareerSource.created_at, CareerSource.id)
            )
        ).all()
    )
    return ScanView(
        **summary(scan).model_dump(),
        resolved_website_url=scan.resolved_website_url,
        resolution_confidence=scan.resolution_confidence,
        resolution_evidence=scan.resolution_evidence,
        candidates=[CandidateView.model_validate(row, from_attributes=True) for row in candidates],
        sources=[CareerSourceView.model_validate(row, from_attributes=True) for row in sources],
        extractions=await latest_for_sources(db, [row.id for row in sources]),
    )


async def owned(
    db: AsyncSession, user_id: UUID, scan_id: UUID, lock: bool = False
) -> DiscoveryScan:
    statement = select(DiscoveryScan).where(
        DiscoveryScan.id == scan_id, DiscoveryScan.user_id == user_id
    )
    if lock:
        statement = statement.with_for_update()
    scan = await db.scalar(statement)
    if scan is None:
        raise DomainError(404, "not_found", "Discovery scan not found")
    return scan


async def listing(
    db: AsyncSession,
    user_id: UUID,
    company_id: UUID | None,
    status: str | None,
    offset: int,
    limit: int,
) -> ScanPage:
    statement = select(DiscoveryScan).where(DiscoveryScan.user_id == user_id)
    if company_id is not None:
        statement = statement.where(DiscoveryScan.company_id == company_id)
    if status is not None:
        statement = statement.where(DiscoveryScan.status == status)
    rows = list(
        (
            await db.scalars(
                statement.order_by(DiscoveryScan.created_at.desc(), DiscoveryScan.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    return ScanPage(
        items=[summary(row) for row in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


async def start(db: AsyncSession, user_id: UUID, company_id: UUID) -> tuple[ScanView, bool]:
    company = await owned_company(db, user_id, company_id)
    active = await db.scalar(
        select(DiscoveryScan)
        .where(DiscoveryScan.company_id == company_id, DiscoveryScan.status.in_(ACTIVE))
        .order_by(DiscoveryScan.created_at.desc())
    )
    if active is not None:
        return await view(db, active), False
    selected_url = company.careers_url or company.website_url
    status = "queued" if selected_url else "needs_input"
    scan = DiscoveryScan(
        user_id=user_id,
        company_id=company_id,
        status=status,
        selected_url=selected_url,
        resolution_evidence=[],
    )
    db.add(scan)
    try:
        await db.flush()
        if selected_url:
            db.add(ScanOutbox(scan_id=scan.id))
        else:
            candidate_url = name_candidate(company.name)
            if candidate_url:
                db.add(
                    DiscoveryCandidate(
                        scan_id=scan.id,
                        url=candidate_url,
                        hostname=urlsplit(candidate_url).hostname or "",
                        confidence="low",
                        evidence=["name_guess_requires_confirmation"],
                    )
                )
        await db.commit()
        await db.refresh(scan)
    except IntegrityError:
        await db.rollback()
        active = await db.scalar(
            select(DiscoveryScan).where(
                DiscoveryScan.company_id == company_id, DiscoveryScan.status.in_(ACTIVE)
            )
        )
        if active is None:
            raise
        return await view(db, active), False
    return await view(db, scan), True


async def select_candidate(
    db: AsyncSession,
    user_id: UUID,
    scan_id: UUID,
    data: ScanSelection,
    at: datetime,
) -> ScanView:
    scan = await owned(db, user_id, scan_id, lock=True)
    existing = await db.scalar(select(DiscoveryScan).where(DiscoveryScan.parent_scan_id == scan.id))
    if existing is not None:
        return await view(db, existing)
    if scan.status != "needs_input":
        raise DomainError(409, "scan_state_conflict", "Scan does not require a selection")
    selected_url = data.website_url
    if data.candidate_id is not None:
        candidate = await db.scalar(
            select(DiscoveryCandidate).where(
                DiscoveryCandidate.id == data.candidate_id,
                DiscoveryCandidate.scan_id == scan.id,
            )
        )
        if candidate is None:
            raise DomainError(404, "not_found", "Discovery candidate not found")
        selected_url = candidate.url
    child = DiscoveryScan(
        user_id=user_id,
        company_id=scan.company_id,
        parent_scan_id=scan.id,
        status="queued",
        selected_url=selected_url,
        resolution_evidence=[],
    )
    scan.status = "superseded"
    scan.completed_at = at
    db.add(child)
    await db.flush()
    db.add(ScanOutbox(scan_id=child.id))
    try:
        await db.commit()
        await db.refresh(child)
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(DiscoveryScan).where(DiscoveryScan.parent_scan_id == scan.id)
        )
        if existing is None:
            raise
        return await view(db, existing)
    return await view(db, child)
