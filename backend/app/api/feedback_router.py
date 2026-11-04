from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import get_db, Feedback
from app.models.user import User
from app.api.auth_router import get_current_user

router = APIRouter(tags=["feedback"])


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    category: str = Field(min_length=2, max_length=80)
    liked: str = Field(default='', max_length=2000)
    improve: str = Field(default='', max_length=2000)
    comment: str = Field(default='', max_length=3000)
    is_bug_report: bool = False
    is_feature_request: bool = False
    public_consent: bool = False


class AdminPatchIn(BaseModel):
    admin_status: str | None = None
    admin_note: str | None = None
    is_published: bool | None = None


# ── User Endpoints ─────────────────────────────────────────────────────────────

@router.post("/api/feedback")
def submit_feedback(data: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fb = Feedback(
        user_id=user.id,
        rating=data.rating,
        category=data.category,
        liked=data.liked.strip(),
        improve=data.improve.strip(),
        comment=data.comment.strip(),
        is_bug_report=data.is_bug_report,
        is_feature_request=data.is_feature_request,
        public_consent=data.public_consent,
        is_published=False,
        admin_status='new',
    )
    db.add(fb)
    db.commit()
    return {
        'message': 'Feedback saved privately. Thank you! Public display requires explicit consent and review.',
        'id': fb.id,
    }


@router.get("/api/feedback/mine")
def my_feedback(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Feedback).where(Feedback.user_id == user.id).order_by(Feedback.created_at.desc())).all()
    return {'feedback': [
        {
            'id': f.id, 'rating': f.rating, 'category': f.category,
            'liked': f.liked, 'improve': f.improve, 'comment': f.comment,
            'is_bug_report': f.is_bug_report, 'is_feature_request': f.is_feature_request,
            'public_consent': f.public_consent, 'is_published': f.is_published,
            'admin_status': f.admin_status,
            'created_at': f.created_at.isoformat(),
        }
        for f in rows
    ]}


@router.delete("/api/feedback/{feedback_id}")
def delete_feedback(feedback_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fb = db.scalars(select(Feedback).where(Feedback.id == feedback_id, Feedback.user_id == user.id)).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found.")
    db.delete(fb)
    db.commit()
    return {'message': 'Feedback deleted.'}


# ── Public Reviews ─────────────────────────────────────────────────────────────

@router.get("/api/reviews")
def public_reviews(db: Session = Depends(get_db)):
    """Only returns reviews with explicit consent AND admin approval (is_published=True)."""
    rows = db.scalars(
        select(Feedback)
        .where(Feedback.public_consent == True, Feedback.is_published == True)
        .order_by(Feedback.created_at.desc())
        .limit(50)
    ).all()

    if not rows:
        return {'reviews': [], 'average_rating': None, 'total_published': 0}

    avg = round(sum(r.rating for r in rows) / len(rows), 1)
    distribution = {str(i): sum(1 for r in rows if r.rating == i) for i in range(1, 6)}

    return {
        'reviews': [
            {
                'id': r.id,
                'rating': r.rating,
                'category': r.category,
                'comment': r.comment,
                'created_at': r.created_at.isoformat(),
            }
            for r in rows
        ],
        'average_rating': avg,
        'total_published': len(rows),
        'distribution': distribution,
    }


# ── Admin Endpoints ────────────────────────────────────────────────────────────

def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


@router.get("/api/admin/feedback")
def admin_list_feedback(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(200)).all()
    return {'feedback': [
        {
            'id': f.id, 'user_id': f.user_id, 'rating': f.rating, 'category': f.category,
            'liked': f.liked, 'improve': f.improve, 'comment': f.comment,
            'is_bug_report': f.is_bug_report, 'is_feature_request': f.is_feature_request,
            'public_consent': f.public_consent, 'is_published': f.is_published,
            'admin_status': f.admin_status, 'admin_note': f.admin_note,
            'created_at': f.created_at.isoformat(),
        }
        for f in rows
    ]}


@router.patch("/api/admin/feedback/{feedback_id}")
def admin_patch_feedback(feedback_id: str, data: AdminPatchIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    fb = db.scalars(select(Feedback).where(Feedback.id == feedback_id)).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found.")
    if data.admin_status is not None:
        fb.admin_status = data.admin_status
    if data.admin_note is not None:
        fb.admin_note = data.admin_note
    # Only allow publishing when user also gave consent
    if data.is_published is not None:
        if data.is_published and not fb.public_consent:
            raise HTTPException(status_code=400, detail="Cannot publish — user did not give public consent.")
        fb.is_published = data.is_published
    db.commit()
    return {'message': 'Feedback updated.', 'id': fb.id}
