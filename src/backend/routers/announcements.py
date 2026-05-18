"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=1, max_length=1000)
    expires_at: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    starts_at: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class AnnouncementUpdatePayload(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    message: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    expires_at: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    starts_at: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def _require_teacher(username: Optional[str]) -> Dict[str, Any]:
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _validate_dates(starts_at: Optional[str], expires_at: str) -> None:
    expires_date = date.fromisoformat(expires_at)
    starts_date = date.fromisoformat(starts_at) if starts_at else None

    if starts_date and starts_date > expires_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after expiration date")


def _announcement_to_response(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("_id"),
        "title": doc.get("title"),
        "message": doc.get("message"),
        "starts_at": doc.get("starts_at"),
        "expires_at": doc.get("expires_at"),
        "created_by": doc.get("created_by")
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_announcements(
    include_all: bool = Query(False),
    teacher_username: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """Get announcements. Public users receive active announcements only."""
    query: Dict[str, Any] = {}

    if include_all:
        _require_teacher(teacher_username)
    else:
        today = date.today().isoformat()
        query = {
            "$and": [
                {"expires_at": {"$gte": today}},
                {
                    "$or": [
                        {"starts_at": None},
                        {"starts_at": {"$exists": False}},
                        {"starts_at": {"$lte": today}}
                    ]
                }
            ]
        }

    docs = announcements_collection.find(query).sort("expires_at", 1)
    return [_announcement_to_response(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement. Requires teacher authentication."""
    _require_teacher(teacher_username)
    _validate_dates(payload.starts_at, payload.expires_at)

    announcement_id = f"announcement-{int(date.today().strftime('%Y%m%d'))}-{announcements_collection.count_documents({}) + 1}"
    doc = {
        "_id": announcement_id,
        "title": payload.title.strip(),
        "message": payload.message.strip(),
        "starts_at": payload.starts_at,
        "expires_at": payload.expires_at,
        "created_by": teacher_username
    }
    announcements_collection.insert_one(doc)
    return _announcement_to_response(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdatePayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement. Requires teacher authentication."""
    _require_teacher(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = {
        "title": payload.title.strip() if payload.title is not None else existing.get("title"),
        "message": payload.message.strip() if payload.message is not None else existing.get("message"),
        "starts_at": payload.starts_at if payload.starts_at is not None else existing.get("starts_at"),
        "expires_at": payload.expires_at if payload.expires_at is not None else existing.get("expires_at")
    }

    _validate_dates(updated["starts_at"], updated["expires_at"])

    announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "title": updated["title"],
                "message": updated["message"],
                "starts_at": updated["starts_at"],
                "expires_at": updated["expires_at"]
            }
        }
    )

    latest = announcements_collection.find_one({"_id": announcement_id})
    return _announcement_to_response(latest)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement. Requires teacher authentication."""
    _require_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
