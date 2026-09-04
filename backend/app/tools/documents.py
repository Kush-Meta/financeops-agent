"""Document retrieval over supporting finance documents."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Document
from app.tools.base import ToolResult, register_tool


@register_tool("search_documents")
def search_documents(
    db: Session,
    query: str,
    doc_type: Optional[str] = None,
    period: Optional[str] = None,
    limit: int = 10,
) -> ToolResult:
    q = select(Document)
    terms = [t.strip() for t in query.split() if t.strip()]
    if terms:
        clauses = []
        for term in terms:
            like = f"%{term}%"
            clauses.append(Document.title.ilike(like))
            clauses.append(Document.content.ilike(like))
            clauses.append(Document.filename.ilike(like))
        q = q.where(or_(*clauses))
    if doc_type:
        q = q.where(Document.doc_type == doc_type)
    if period:
        q = q.where(Document.period == period)
    q = q.limit(limit)
    rows = db.execute(q).scalars().all()

    # Simple relevance: count term hits
    scored = []
    lower_terms = [t.lower() for t in terms] or [query.lower()]
    for doc in rows:
        blob = f"{doc.title}\n{doc.content}".lower()
        score = sum(blob.count(t) for t in lower_terms)
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)

    data = [
        {
            "id": doc.id,
            "doc_type": doc.doc_type,
            "title": doc.title,
            "filename": doc.filename,
            "period": doc.period,
            "related_entity_type": doc.related_entity_type,
            "related_entity_id": doc.related_entity_id,
            "tags": doc.tags,
            "snippet": doc.content[:500],
            "relevance": score,
        }
        for score, doc in scored
    ]
    return ToolResult(
        tool="search_documents",
        ok=True,
        data=data,
        summary=f"Found {len(data)} document(s) matching '{query}'",
        records_accessed=[{"type": "document", "id": d["id"]} for d in data],
    )
