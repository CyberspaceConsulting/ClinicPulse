import hashlib
import hmac
import math
import time

from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .models import LoginAttempt

WINDOW_SECONDS = 15 * 60
MAX_TRACKED_KEYS = 10_000


class LoginThrottle:
    @staticmethod
    def _key(client_ip: str, username: str, secret: str) -> str:
        material = f"{client_ip}\0{username.strip().casefold()}".encode()
        return hmac.new(secret.encode(), material, hashlib.sha256).hexdigest()

    def retry_after(
        self,
        db: Session,
        client_ip: str,
        username: str,
        secret: str,
        now: float | None = None,
    ) -> int:
        current_time = time.time() if now is None else now
        removed = db.execute(
            delete(LoginAttempt).where(LoginAttempt.last_seen < current_time - WINDOW_SECONDS)
        ).rowcount
        if removed:
            db.commit()
        state = db.get(LoginAttempt, self._key(client_ip, username, secret))
        if state is None:
            return 0
        return max(0, math.ceil(state.blocked_until - current_time))

    def record_failure(
        self,
        db: Session,
        client_ip: str,
        username: str,
        secret: str,
        now: float | None = None,
    ) -> float:
        current_time = time.time() if now is None else now
        key = self._key(client_ip, username, secret)
        insert = self._insert_for_dialect(db)
        reset_window = current_time - LoginAttempt.window_started_at >= WINDOW_SECONDS
        failure_count = case(
            (reset_window, 1),
            else_=LoginAttempt.failed_attempts + 1,
        )
        blocked_until = case(
            (failure_count >= 10, current_time + WINDOW_SECONDS),
            (failure_count >= 5, current_time + 60),
            (LoginAttempt.blocked_until > current_time, LoginAttempt.blocked_until),
            else_=0,
        )
        statement = insert.values(
            key=key,
            failed_attempts=1,
            window_started_at=current_time,
            blocked_until=0,
            last_seen=current_time,
        ).on_conflict_do_update(
            index_elements=[LoginAttempt.key],
            set_={
                "failed_attempts": failure_count,
                "window_started_at": case(
                    (reset_window, current_time),
                    else_=LoginAttempt.window_started_at,
                ),
                "blocked_until": blocked_until,
                "last_seen": current_time,
            },
        ).returning(LoginAttempt.failed_attempts)
        db.execute(delete(LoginAttempt).where(LoginAttempt.last_seen < current_time - WINDOW_SECONDS))
        failures = db.scalar(statement)
        oldest_keys = (
            select(LoginAttempt.key)
            .order_by(LoginAttempt.last_seen.desc())
            .offset(MAX_TRACKED_KEYS)
        )
        db.execute(delete(LoginAttempt).where(LoginAttempt.key.in_(oldest_keys)))
        db.commit()
        return min(0.5 * (2 ** (failures - 1)), 8)

    @staticmethod
    def _insert_for_dialect(db: Session):
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            return postgresql_insert(LoginAttempt)
        if dialect == "sqlite":
            return sqlite_insert(LoginAttempt)
        raise RuntimeError(f"Login throttling is unsupported for database dialect {dialect}")

    def record_success(self, db: Session, client_ip: str, username: str, secret: str) -> None:
        db.execute(
            delete(LoginAttempt).where(
                LoginAttempt.key == self._key(client_ip, username, secret)
            )
        )
        db.commit()
