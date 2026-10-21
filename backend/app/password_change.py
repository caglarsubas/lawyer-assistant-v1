"""Self-service credential change; no matter, vault or bootstrap configuration writes."""

import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from .auth import authenticate, check_password, hash_password
from .db import Audit, LoginSession, User


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    current_password: SecretStr = Field(min_length=1, max_length=200, repr=False)
    new_password: SecretStr = Field(min_length=16, max_length=200, repr=False)
    confirm_password: SecretStr = Field(min_length=16, max_length=200, repr=False)

    @field_validator("current_password", "new_password", "confirm_password")
    @classmethod
    def supported_characters(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF
               for c in value.get_secret_value()):
            raise ValueError("Parola kontrol karakteri içeremez")
        return value


def password_router():
    router = APIRouter()

    @router.post("/api/v1/auth/password")
    def change_password(body: PasswordChange, request: Request, response: Response,
                        principal=Depends(authenticate)):
        # authenticate holds the exclusive firm guard through the response.
        # Login takes its shared counterpart and rechecks the hash after waiting.
        try:
            with request.app.state.store.session() as session:
                user = session.get(User, principal.id)
                if not user or not user.active or user.firm_id != principal.firm_id:
                    raise HTTPException(401, "Oturum geçersiz")
                since = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                failures = session.scalar(select(func.count()).select_from(Audit).where(
                    Audit.action == "password_change_failed", Audit.object_id == user.id,
                    Audit.created_at >= since,
                ))
                if failures >= 5:
                    raise HTTPException(429, "Çok fazla parola denemesi; beş dakika sonra tekrar deneyin")
                current = body.current_password.get_secret_value()
                new = body.new_password.get_secret_value()
                confirmation = body.confirm_password.get_secret_value()
                if not hmac.compare_digest(new.encode(), confirmation.encode()):
                    raise HTTPException(400, "Yeni parola ve tekrarı eşleşmiyor")
                if not new.strip():
                    raise HTTPException(400, "Yeni parola yalnızca boşluk olamaz")
                if not check_password(current, user.password_hash):
                    session.add(Audit(actor_id=user.id, action="password_change_failed", object_id=user.id))
                    session.commit()
                    raise HTTPException(400, "Mevcut parola doğrulanamadı")
                if hmac.compare_digest(new.encode(), current.encode()):
                    raise HTTPException(400, "Yeni parola mevcut paroladan farklı olmalı")
                changed = session.execute(update(User).where(
                    User.id == user.id, User.password_hash == user.password_hash,
                ).values(password_hash=hash_password(new)))
                if changed.rowcount != 1:
                    raise HTTPException(409, "Hesap değişti; yeniden giriş yapın")
                session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
                session.add(Audit(actor_id=user.id, action="password_changed", object_id=user.id))
                session.commit()
        except SQLAlchemyError:
            raise HTTPException(503, "Parola değişikliği tamamlanamadı; tekrar deneyin") from None
        response.delete_cookie("la_session", path="/", httponly=True,
                               secure=request.app.state.settings.cookie_secure, samesite="strict")
        return {"ok": True, "reauthentication_required": True}

    return router
