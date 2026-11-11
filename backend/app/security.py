import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hmac import compare_digest

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .encrypted import username_lookup_digest
from .license_manager import license_is_read_only
from .models import AdminAccount, ApplicationSetting, LicenseState, UserAccount

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    username: str
    role_key: str
    department_id: int | None
    can_view: bool
    can_edit: bool
    can_approve: bool
    can_manage: bool
    remember_me: bool = False
    department_ids: tuple[int, ...] = ()
    employee_id: int | None = None
    must_change_password: bool = False


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    password_salt = salt or secrets.token_bytes(16)
    password_hash = hashlib.scrypt(password.encode(), salt=password_salt, n=2**14, r=8, p=1)
    return (
        base64.urlsafe_b64encode(password_salt).decode(),
        base64.urlsafe_b64encode(password_hash).decode(),
    )


def verify_password(password_salt: str, password_hash: str, password: str) -> bool:
    salt = base64.urlsafe_b64decode(password_salt.encode())
    _, candidate = hash_password(password, salt)
    return compare_digest(candidate, password_hash)


def get_account(db: Session) -> AdminAccount | None:
    return db.scalar(select(AdminAccount).where(AdminAccount.id == 1))


def create_token_response(
    username: str,
    role_key: str = "ADMIN",
    department_id: int | None = None,
    can_view: bool = True,
    can_edit: bool = True,
    can_approve: bool = True,
    remember_me: bool = False,
) -> dict[str, object]:
    can_manage = role_key in {"ADMIN", "HOSPITAL_MANAGEMENT"}
    return {
        "username": username,
        "role_key": role_key,
        "department_id": department_id,
        "can_view": can_view,
        "can_edit": can_edit,
        "can_approve": can_approve,
        "can_manage": can_manage,
        "remember_me": remember_me,
    }


def issue_token(signing_key: str, subject: str, version: int, remember_me: bool = False) -> str:
    now = datetime.now(timezone.utc)
    expires = now + (
        timedelta(days=30) if remember_me else timedelta(hours=8)
    )
    return jwt.encode(
        {
            "sub": subject,
            "ver": version,
            "exp": expires,
            "last_activity": now.timestamp(),
            "remember_me": remember_me,
        },
        signing_key,
        algorithm=ALGORITHM,
    )


def set_session_cookie(
    response: Response,
    signing_key: str,
    request: Request,
    subject: str,
    version: int,
    remember_me: bool = False,
) -> None:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    response.set_cookie(
        "clinicpulse_session",
        issue_token(signing_key, subject, version, remember_me),
        max_age=30 * 24 * 60 * 60 if remember_me else 8 * 60 * 60,
        httponly=True,
        secure=forwarded_proto == "https",
        samesite="strict",
        path="/",
    )


DEFAULT_IDLE_TIMEOUT_MINUTES = 5


def idle_timeout_minutes(db: Session) -> int:
    settings = db.get(ApplicationSetting, 1)
    value = getattr(settings, "idle_timeout_minutes", None)
    return value if isinstance(value, int) and value > 0 else DEFAULT_IDLE_TIMEOUT_MINUTES


def authenticate(db: Session, username: str, password: str) -> tuple[AdminAccount, Principal, str, int] | None:
    root = get_account(db)
    if root is None:
        return None
    if compare_digest(username, root.username) and verify_password(root.password_salt, root.password_hash, password):
        return (
            root,
            Principal(root.username, "ADMIN", None, True, True, True, True),
            "a:1",
            root.token_version,
        )
    user = db.scalar(
        select(UserAccount).where(
            UserAccount.username_lookup == username_lookup_digest(username)
        )
    )
    if user is None or user.is_locked or not verify_password(user.password_salt, user.password_hash, password):
        return None
    return (
        root,
        Principal(
            user.username,
            user.role_key,
            user.department_id,
            user.can_view,
            user.can_edit,
            user.can_approve,
            user.role_key == "HOSPITAL_MANAGEMENT",
            False,
            tuple(user.department_ids or ([user.department_id] if user.department_id is not None else [])),
            user.employee_id,
            user.must_change_password,
        ),
        f"u:{user.id}",
        user.token_version,
    )


def require_principal(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session_cookie: str | None = Cookie(default=None, alias="clinicpulse_session"),
    db: Session = Depends(get_db),
) -> Principal:
    encoded_token = credentials.credentials if credentials is not None else session_cookie
    if encoded_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    root = get_account(db)
    if root is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Setup required")
    try:
        payload = jwt.decode(encoded_token, root.signing_key, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session") from exc
    subject = payload.get("sub")
    version = payload.get("ver")
    remember_me_claim = payload.get("remember_me", False)
    last_activity_claim = payload.get("last_activity")
    if not isinstance(remember_me_claim, bool):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    remember_me = remember_me_claim
    now = datetime.now(timezone.utc)
    if last_activity_claim is None:
        last_activity = now
    elif isinstance(last_activity_claim, (int, float)) and not isinstance(last_activity_claim, bool):
        try:
            last_activity = datetime.fromtimestamp(last_activity_claim, timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session") from exc
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    if subject == "a:1" and version == root.token_version and not remember_me:
        principal = Principal(root.username, "ADMIN", None, True, True, True, True)
        db.info["audit_actor"] = principal.username
        idle_timeout = timedelta(minutes=idle_timeout_minutes(db))
        if credentials is None and now - last_activity >= idle_timeout:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired due to inactivity")
        if credentials is None and response is not None and request is not None:
            set_session_cookie(response, root.signing_key, request, "a:1", version)
        return principal
    if isinstance(subject, str) and subject.startswith("u:"):
        try:
            user_id = int(subject[2:])
        except ValueError:
            user_id = 0
        user = db.get(UserAccount, user_id)
        if user is not None and not user.is_locked and version == user.token_version:
            principal = Principal(
                user.username,
                user.role_key,
                user.department_id,
                user.can_view,
                user.can_edit,
                user.can_approve,
                user.role_key == "HOSPITAL_MANAGEMENT",
                remember_me,
                tuple(user.department_ids or ([user.department_id] if user.department_id is not None else [])),
                user.employee_id,
                user.must_change_password,
            )
            if user.must_change_password and (request.method, request.url.path) not in {
                ("GET", "/api/auth/session"),
                ("PUT", "/api/settings/account"),
            }:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required")
            db.info["audit_actor"] = principal.username
            if credentials is None and principal.role_key != "KIOSK" and now - last_activity >= timedelta(minutes=idle_timeout_minutes(db)):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired due to inactivity")
            if credentials is None and response is not None and request is not None:
                set_session_cookie(
                    response,
                    root.signing_key,
                    request,
                    subject,
                    version,
                    remember_me,
                )
            return principal
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")


def require_admin(principal: Principal = Depends(require_principal)) -> Principal:
    if principal.role_key != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return principal


def require_manage(principal: Principal = Depends(require_principal)) -> Principal:
    if not principal.can_manage:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Department and account management access required")
    return principal


def require_team_manage(principal: Principal = Depends(require_principal)) -> Principal:
    if principal.role_key not in {"ADMIN", "HOSPITAL_MANAGEMENT", "PERSONNEL"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Team management access required")
    return principal


def require_view(principal: Principal = Depends(require_principal)) -> Principal:
    if not principal.can_view and not principal.can_manage:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Schedule view permission required")
    return principal


def require_plan_view(principal: Principal = Depends(require_view)) -> Principal:
    if principal.role_key == "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dienstpläne sind für den Administrator nicht einsehbar")
    if not principal.can_view:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Schedule view permission required")
    return principal


def require_edit(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> Principal:
    if principal.role_key != "OBERARZT" or not principal.can_edit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Schedule editing permission required")
    license_state = db.get(LicenseState, 1)
    account = get_account(db)
    read_only, reason = license_is_read_only(
        license_state.signed_status_token if license_state else None,
        license_state.last_successful_check_at if license_state else None,
        license_token=account.license_token if account else None,
        installation_id=license_state.installation_id if license_state else None,
    )
    if read_only:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=f"License is read-only: {reason}")
    return principal


def require_approve(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> Principal:
    if principal.role_key != "OBERARZT" or not principal.can_approve:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Schedule approval permission required")
    license_state = db.get(LicenseState, 1)
    account = get_account(db)
    read_only, reason = license_is_read_only(
        license_state.signed_status_token if license_state else None,
        license_state.last_successful_check_at if license_state else None,
        license_token=account.license_token if account else None,
        installation_id=license_state.installation_id if license_state else None,
    )
    if read_only:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=f"License is read-only: {reason}")
    return principal


def require_license_writable(db: Session = Depends(get_db)) -> None:
    license_state = db.get(LicenseState, 1)
    account = get_account(db)
    read_only, reason = license_is_read_only(
        license_state.signed_status_token if license_state else None,
        license_state.last_successful_check_at if license_state else None,
        license_token=account.license_token if account else None,
        installation_id=license_state.installation_id if license_state else None,
    )
    if read_only:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=f"License is read-only: {reason}")
