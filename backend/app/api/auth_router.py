from __future__ import annotations
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email import send_transactional_email, build_otp_email
from app.core.rate_limit import check_rate_limit
from app.core.security import (
    hash_password, verify_password, normalize_email, utcnow,
    otp_digest, verify_otp_digest, generate_otp, generate_session_token, token_digest,
)
from app.models import get_db, User, Challenge, UserSession

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r'^\d{6}$')

class ResendIn(BaseModel):
    email: EmailStr

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class ForgotIn(BaseModel):
    email: EmailStr

class ResetIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r'^\d{6}$')
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)


# ── Helpers ───────────────────────────────────────────────────────────────────

def create_session(db: Session, user: User, response: Response) -> None:
    token = generate_session_token()
    db.add(UserSession(
        user_id=user.id,
        token_hash=token_digest(token),
        expires_at=utcnow() + timedelta(days=settings.session_days),
    ))
    db.commit()
    response.set_cookie(
        'dp_session', token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path='/',
        max_age=settings.session_days * 86400,
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get('dp_session')
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in.")
    sess = db.scalars(select(UserSession).where(UserSession.token_hash == token_digest(token))).first()
    if not sess:
        raise HTTPException(status_code=401, detail="Session not found. Please sign in again.")
    if sess.expires_at.replace(tzinfo=utcnow().tzinfo if sess.expires_at.tzinfo is None else sess.expires_at.tzinfo) <= utcnow():
        db.delete(sess)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    user = db.get(User, sess.user_id)
    if not user or not user.verified:
        raise HTTPException(status_code=401, detail="Account not found or not verified.")
    return user


def issue_challenge(db: Session, user: User, purpose: str) -> None:
    # Enforce resend cooldown
    last = db.scalars(
        select(Challenge)
        .where(Challenge.user_id == user.id, Challenge.purpose == purpose, Challenge.used == False)
        .order_by(Challenge.last_sent_at.desc())
    ).first()
    if last and (utcnow() - last.last_sent_at).total_seconds() < settings.otp_resend_seconds:
        raise HTTPException(status_code=429, detail=f"Please wait {settings.otp_resend_seconds} seconds before requesting another code.")

    code = generate_otp()
    title, html, text = build_otp_email(user.email, code, purpose)
    # Send first — only persist after successful delivery
    send_transactional_email(user.email, title, html, text)

    # Invalidate old pending codes
    for ch in db.scalars(select(Challenge).where(Challenge.user_id == user.id, Challenge.purpose == purpose, Challenge.used == False)).all():
        ch.used = True

    db.add(Challenge(
        user_id=user.id,
        purpose=purpose,
        digest=otp_digest(code),
        expires_at=utcnow() + timedelta(minutes=settings.otp_ttl_minutes),
        attempts=0,
        last_sent_at=utcnow(),
    ))
    db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 'register')
    if data.password != data.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")
    email = normalize_email(str(data.email))
    # Generic response to prevent email enumeration
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email may already exist. Try signing in or resetting your password.")
    user = User(name=data.name.strip(), email=email, password_hash=hash_password(data.password), verified=False)
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create account. Please try again.")
    issue_challenge(db, user, 'verify')
    return {
        'message': 'Verification code sent. Check your email inbox.',
        'email': user.email,
        'expires_in_seconds': settings.otp_ttl_minutes * 60,
    }


@router.post("/verify-email")
def verify_email(data: VerifyIn, response: Response, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 'verify')
    email = normalize_email(str(data.email))
    user = db.scalars(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    if user.verified:
        create_session(db, user, response)
        return {'message': 'Already verified. Signed in.', 'user': {'id': user.id, 'name': user.name, 'email': user.email}}

    ch = db.scalars(
        select(Challenge)
        .where(Challenge.user_id == user.id, Challenge.purpose == 'verify', Challenge.used == False)
        .order_by(Challenge.last_sent_at.desc())
    ).first()

    if not ch or ch.expires_at.replace(tzinfo=utcnow().tzinfo) <= utcnow() or ch.attempts >= settings.otp_max_attempts:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    ch.attempts += 1
    if not verify_otp_digest(data.code, ch.digest):
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    ch.used = True
    user.verified = True
    db.commit()
    create_session(db, user, response)
    return {'message': 'Email verified! Welcome to DataPilot AI.', 'user': {'id': user.id, 'name': user.name, 'email': user.email}}


@router.post("/resend-otp")
def resend_otp(data: ResendIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 'resend')
    email = normalize_email(str(data.email))
    user = db.scalars(select(User).where(User.email == email)).first()
    if user and not user.verified:
        try:
            issue_challenge(db, user, 'verify')
        except HTTPException as e:
            if e.status_code == 429:
                raise
    return {'message': 'If a pending account exists, a new code will be delivered when the cooldown period has elapsed.'}


@router.post("/login")
def login(data: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 'login')
    email = normalize_email(str(data.email))
    user = db.scalars(select(User).where(User.email == email)).first()
    ok = bool(user and verify_password(user.password_hash, data.password))
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.verified:
        raise HTTPException(status_code=403, detail="Please verify your email address before signing in.")
    create_session(db, user, response)
    return {'message': 'Signed in successfully.', 'user': {'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin}}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get('dp_session')
    if token:
        sess = db.scalars(select(UserSession).where(UserSession.token_hash == token_digest(token))).first()
        if sess:
            db.delete(sess)
            db.commit()
    response.delete_cookie('dp_session', path='/', secure=settings.cookie_secure, httponly=True, samesite=settings.cookie_samesite)
    return {'message': 'Signed out successfully.'}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {'user': {'id': user.id, 'name': user.name, 'email': user.email, 'is_admin': user.is_admin}}


@router.post("/forgot-password")
def forgot_password(data: ForgotIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 'forgot')
    email = normalize_email(str(data.email))
    user = db.scalars(select(User).where(User.email == email)).first()
    if user and user.verified:
        try:
            issue_challenge(db, user, 'reset')
        except HTTPException as e:
            if e.status_code == 429:
                raise
    return {'message': 'If a verified account exists for this email, reset instructions have been sent.'}


@router.post("/reset-password")
def reset_password(data: ResetIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 'reset')
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")
    email = normalize_email(str(data.email))
    user = db.scalars(select(User).where(User.email == email)).first()
    ch = None
    if user:
        ch = db.scalars(
            select(Challenge)
            .where(Challenge.user_id == user.id, Challenge.purpose == 'reset', Challenge.used == False)
            .order_by(Challenge.last_sent_at.desc())
        ).first()

    if not user or not ch or ch.expires_at.replace(tzinfo=utcnow().tzinfo) <= utcnow() or ch.attempts >= settings.otp_max_attempts:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")

    ch.attempts += 1
    if not verify_otp_digest(data.code, ch.digest):
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")

    ch.used = True
    user.password_hash = hash_password(data.new_password)
    # Invalidate all existing sessions
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all():
        db.delete(s)
    db.commit()
    return {'message': 'Password updated successfully. Please sign in with your new password.'}
