"""Database-backed repositories — replace in-memory stores."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.core.logging import get_logger
from evidentia.core.models import (
    Citation,
    Claim,
    ClaimConfidence,
    EvidenceSpan,
    Source,
    SourceType,
)
from evidentia.db.models import (
    AnnotationRow,
    CitationRow,
    ClaimRow,
    DocumentRow,
    EvidenceSpanRow,
    PDFChunkRow,
    PDFUploadRow,
    ProjectRow,
    ResearchMemoryRow,
    RunRow,
    TeamMemberRow,
    TeamRow,
    UserRow,
)

logger = get_logger(__name__)


# ── User Repository ─────────────────────────────────────────────────


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, email: str, hashed_password: str) -> UserRow:
        user = UserRow(
            email=email,
            hashed_password=hashed_password,
            api_key=secrets.token_hex(32),
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_email(self, email: str) -> UserRow | None:
        result = await self._session.execute(
            select(UserRow).where(UserRow.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> UserRow | None:
        return await self._session.get(UserRow, user_id)

    async def get_by_api_key(self, api_key: str) -> UserRow | None:
        result = await self._session.execute(
            select(UserRow).where(UserRow.api_key == api_key)
        )
        return result.scalar_one_or_none()

    async def regenerate_api_key(self, user_id: uuid.UUID) -> str:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        user.api_key = secrets.token_hex(32)
        await self._session.flush()
        return user.api_key


# ── Run Repository ──────────────────────────────────────────────────


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_run(
        self,
        user_id: uuid.UUID,
        query: str,
        summary: str,
        claims: list[Claim],
        plan_json: dict | None,
        evidence_summary: dict | None,
        total_tool_calls: int,
        total_iterations: int,
        elapsed_seconds: float,
        success: bool,
        project_id: uuid.UUID | None = None,
    ) -> RunRow:
        run = RunRow(
            user_id=user_id,
            project_id=project_id,
            query=query,
            status="completed" if success else "failed",
            summary=summary,
            plan_json=plan_json,
            evidence_summary_json=evidence_summary,
            total_tool_calls=total_tool_calls,
            total_iterations=total_iterations,
            elapsed_seconds=elapsed_seconds,
            completed_at=datetime.now(timezone.utc),
        )
        self._session.add(run)
        await self._session.flush()

        # Save claims with citations and evidence
        for i, claim in enumerate(claims):
            claim_row = ClaimRow(
                run_id=run.id,
                statement=claim.statement,
                confidence=claim.confidence.value,
                position=i,
            )
            self._session.add(claim_row)
            await self._session.flush()

            for cit in claim.citations:
                self._session.add(CitationRow(
                    claim_id=claim_row.id,
                    source_id=cit.source_id,
                    title=cit.title,
                    authors_json=cit.authors,
                    url=cit.url,
                    doi=cit.doi,
                    published_date=cit.published_date,
                ))

            for ev in claim.evidence_spans:
                self._session.add(EvidenceSpanRow(
                    claim_id=claim_row.id,
                    source_id=ev.source_id,
                    text=ev.text,
                    start_offset=ev.start_offset,
                    end_offset=ev.end_offset,
                    is_conflicting=False,
                ))

            for ev in claim.conflicting_evidence:
                self._session.add(EvidenceSpanRow(
                    claim_id=claim_row.id,
                    source_id=ev.source_id,
                    text=ev.text,
                    start_offset=ev.start_offset,
                    end_offset=ev.end_offset,
                    is_conflicting=True,
                ))

        await self._session.flush()
        return run

    async def get_run(self, run_id: uuid.UUID) -> RunRow | None:
        return await self._session.get(RunRow, run_id)

    async def list_runs(self, user_id: uuid.UUID, limit: int = 20) -> list[RunRow]:
        result = await self._session.execute(
            select(RunRow)
            .where(RunRow.user_id == user_id)
            .order_by(RunRow.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def run_to_claims(self, run: RunRow) -> list[Claim]:
        """Convert RunRow with loaded relationships to domain Claim objects."""
        claims: list[Claim] = []
        for cr in sorted(run.claims, key=lambda c: c.position):
            citations = [
                Citation(
                    source_id=c.source_id,
                    title=c.title,
                    authors=c.authors_json or [],
                    url=c.url,
                    doi=c.doi,
                    published_date=c.published_date,
                )
                for c in cr.citations
            ]
            evidence = [
                EvidenceSpan(
                    source_id=e.source_id,
                    text=e.text,
                    start_offset=e.start_offset,
                    end_offset=e.end_offset,
                )
                for e in cr.evidence_spans if not e.is_conflicting
            ]
            conflicting = [
                EvidenceSpan(
                    source_id=e.source_id,
                    text=e.text,
                    start_offset=e.start_offset,
                    end_offset=e.end_offset,
                )
                for e in cr.evidence_spans if e.is_conflicting
            ]
            claims.append(Claim(
                id=str(cr.id),
                statement=cr.statement,
                confidence=ClaimConfidence(cr.confidence),
                citations=citations,
                evidence_spans=evidence,
                conflicting_evidence=conflicting,
            ))
        return claims


# ── Project Repository ──────────────────────────────────────────────


class AnnotationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        run_id: uuid.UUID | None,
        text: str,
        claim_id: str | None = None,
        annotation_type: str = "note",
    ) -> AnnotationRow:
        annotation = AnnotationRow(
            user_id=user_id,
            run_id=run_id,
            claim_id=claim_id,
            text=text,
            annotation_type=annotation_type,
        )
        self._session.add(annotation)
        await self._session.flush()
        return annotation

    async def list_by_run(self, run_id: uuid.UUID) -> list[AnnotationRow]:
        result = await self._session.execute(
            select(AnnotationRow)
            .where(AnnotationRow.run_id == run_id)
            .order_by(AnnotationRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete(self, annotation_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(AnnotationRow).where(AnnotationRow.id == annotation_id)
        )
        return result.rowcount > 0  # type: ignore[return-value]


class ResearchMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        user_id: uuid.UUID,
        topic_summary: str,
        source_ids: list[str],
    ) -> ResearchMemoryRow:
        memory = ResearchMemoryRow(
            user_id=user_id,
            topic_summary=topic_summary,
            source_ids_json=source_ids,
        )
        self._session.add(memory)
        await self._session.flush()
        return memory

    async def find_related(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int = 3,
    ) -> list[ResearchMemoryRow]:
        """Simple keyword matching on topic_summary. Upgradeable to pgvector."""
        result = await self._session.execute(
            select(ResearchMemoryRow)
            .where(ResearchMemoryRow.user_id == user_id)
            .order_by(ResearchMemoryRow.last_accessed.desc())
            .limit(50)
        )
        all_memories = list(result.scalars().all())

        # Score by keyword overlap
        query_words = set(query.lower().split())
        scored = []
        for mem in all_memories:
            summary_words = set(mem.topic_summary.lower().split())
            overlap = len(query_words & summary_words)
            if overlap > 0:
                scored.append((overlap, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:top_k]]


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: uuid.UUID, name: str, description: str = "") -> ProjectRow:
        project = ProjectRow(
            user_id=user_id,
            name=name,
            description=description,
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def get(self, project_id: uuid.UUID) -> ProjectRow | None:
        return await self._session.get(ProjectRow, project_id)

    async def list_by_user(self, user_id: uuid.UUID) -> list[ProjectRow]:
        result = await self._session.execute(
            select(ProjectRow)
            .where(ProjectRow.user_id == user_id)
            .order_by(ProjectRow.updated_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, project_id: uuid.UUID, **kwargs: Any) -> ProjectRow | None:
        project = await self.get(project_id)
        if project is None:
            return None
        for key, value in kwargs.items():
            if hasattr(project, key):
                setattr(project, key, value)
        project.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return project

    async def delete(self, project_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(ProjectRow).where(ProjectRow.id == project_id)
        )
        return result.rowcount > 0  # type: ignore[return-value]

    async def get_runs(self, project_id: uuid.UUID, limit: int = 50) -> list[RunRow]:
        result = await self._session.execute(
            select(RunRow)
            .where(RunRow.project_id == project_id)
            .order_by(RunRow.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# ── Document Repository ─────────────────────────────────────────────


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, source: Source, user_id: uuid.UUID | None = None) -> DocumentRow:
        content_hash = hashlib.sha256(source.content.encode()).hexdigest()

        # Deduplicate by content hash
        existing = await self._session.execute(
            select(DocumentRow).where(DocumentRow.content_hash == content_hash)
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return row

        row = DocumentRow(
            user_id=user_id,
            source_type=source.source_type.value,
            title=source.title,
            content=source.content,
            content_hash=content_hash,
            url=source.url,
            doi=source.doi,
            metadata_json=source.metadata,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, doc_id: uuid.UUID) -> DocumentRow | None:
        return await self._session.get(DocumentRow, doc_id)

    async def list_all(self, user_id: uuid.UUID | None = None, limit: int = 100) -> list[DocumentRow]:
        stmt = select(DocumentRow).limit(limit)
        if user_id is not None:
            stmt = stmt.where(DocumentRow.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, doc_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(DocumentRow).where(DocumentRow.id == doc_id)
        )
        return result.rowcount > 0  # type: ignore[return-value]


# ── PDF Repository ──────────────────────────────────────────────────


class PDFRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        user_id: uuid.UUID | None,
        filename: str,
        page_count: int,
        chunk_count: int,
        text: str,
        metadata: dict[str, Any],
        file_path: str,
        chunks: list[dict[str, Any]],
    ) -> PDFUploadRow:
        pdf = PDFUploadRow(
            user_id=user_id,
            filename=filename,
            page_count=page_count,
            chunk_count=chunk_count,
            text=text,
            metadata_json=metadata,
            file_path=file_path,
        )
        self._session.add(pdf)
        await self._session.flush()

        for chunk in chunks:
            self._session.add(PDFChunkRow(
                pdf_id=pdf.id,
                text=chunk.get("text", ""),
                page_number=chunk.get("page_number", 0),
                chunk_index=chunk.get("chunk_index", 0),
            ))
        await self._session.flush()
        return pdf

    async def get(self, pdf_id: uuid.UUID) -> PDFUploadRow | None:
        return await self._session.get(PDFUploadRow, pdf_id)

    async def list_all(self, user_id: uuid.UUID | None = None) -> list[PDFUploadRow]:
        stmt = select(PDFUploadRow).order_by(PDFUploadRow.created_at.desc())
        if user_id is not None:
            stmt = stmt.where(PDFUploadRow.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, pdf_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(PDFUploadRow).where(PDFUploadRow.id == pdf_id)
        )
        return result.rowcount > 0  # type: ignore[return-value]


# ── Team Repository ────────────────────────────────────────────────


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str, created_by: uuid.UUID) -> TeamRow:
        team = TeamRow(name=name, created_by=created_by)
        self._session.add(team)
        await self._session.flush()
        # Creator is auto-added as admin
        member = TeamMemberRow(
            team_id=team.id,
            user_id=created_by,
            role="admin",
        )
        self._session.add(member)
        await self._session.flush()
        return team

    async def get(self, team_id: uuid.UUID) -> TeamRow | None:
        return await self._session.get(TeamRow, team_id)

    async def list_by_user(self, user_id: uuid.UUID) -> list[TeamRow]:
        result = await self._session.execute(
            select(TeamRow)
            .join(TeamMemberRow, TeamRow.id == TeamMemberRow.team_id)
            .where(TeamMemberRow.user_id == user_id)
            .order_by(TeamRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_member(
        self, team_id: uuid.UUID, user_id: uuid.UUID, role: str = "viewer"
    ) -> TeamMemberRow:
        member = TeamMemberRow(team_id=team_id, user_id=user_id, role=role)
        self._session.add(member)
        await self._session.flush()
        return member

    async def remove_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(TeamMemberRow).where(
                TeamMemberRow.team_id == team_id,
                TeamMemberRow.user_id == user_id,
            )
        )
        return result.rowcount > 0  # type: ignore[return-value]

    async def is_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(TeamMemberRow).where(
                TeamMemberRow.team_id == team_id,
                TeamMemberRow.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_member_role(self, team_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        result = await self._session.execute(
            select(TeamMemberRow).where(
                TeamMemberRow.team_id == team_id,
                TeamMemberRow.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        return member.role if member else None
