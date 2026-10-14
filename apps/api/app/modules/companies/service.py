import hashlib
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.core.values import comparison_key
from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyInput, CompanyPage, CompanyView


def identity_key(data: CompanyInput) -> str:
    value = (
        f"website:{data.website_url}"
        if data.website_url
        else f"careers:{data.careers_url}"
        if data.careers_url
        else f"name:{comparison_key(data.name or '')}"
    )
    return hashlib.sha256(value.encode()).hexdigest()


def view(company: Company) -> CompanyView:
    return CompanyView(
        id=company.id,
        name=company.name,
        website_url=company.website_url,
        careers_url=company.careers_url,
        display_label=company.name
        or urlsplit(company.website_url or company.careers_url or "").hostname
        or "",
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


async def owned(db: AsyncSession, user_id: UUID, company_id: UUID) -> Company:
    company = await db.scalar(
        select(Company).where(Company.id == company_id, Company.user_id == user_id)
    )
    if company is None:
        raise DomainError(404, "not_found", "Company not found")
    return company


async def listing(db: AsyncSession, user_id: UUID, offset: int, limit: int) -> CompanyPage:
    rows = list(
        (
            await db.scalars(
                select(Company)
                .where(Company.user_id == user_id)
                .order_by(Company.created_at.desc(), Company.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    return CompanyPage(
        items=[view(row) for row in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


async def save(
    db: AsyncSession, user_id: UUID, data: CompanyInput, company_id: UUID | None = None
) -> CompanyView:
    company = await owned(db, user_id, company_id) if company_id else Company(user_id=user_id)
    company.name, company.website_url, company.careers_url = (
        data.name,
        data.website_url,
        data.careers_url,
    )
    company.identity_key = identity_key(data)
    db.add(company)
    try:
        await db.flush()
        await db.refresh(company)
        result = view(company)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise DomainError(409, "company_duplicate", "This company is already saved") from None
        raise
    return result


async def remove(db: AsyncSession, user_id: UUID, company_id: UUID) -> None:
    await db.delete(await owned(db, user_id, company_id))
    await db.commit()
