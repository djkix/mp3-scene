import hashlib
import secrets
import threading

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

SESSION_TTL = 30 * 86400
DAY = 86400
COOKIE = "session"

_hasher = PasswordHasher()
# vérifié pour un identifiant inconnu, afin que la durée de réponse ne trahisse pas son existence
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(hash: str, pw: str) -> bool:
    try:
        return _hasher.verify(hash, pw)
    except (VerificationError, InvalidHashError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: int, now: float) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    conn.execute("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?,?,?)",
                 (_token_hash(token), user_id, now + SESSION_TTL))
    conn.commit()
    return token


def session_user(conn, token: str, now: float):
    h = _token_hash(token)
    row = conn.execute("SELECT u.id, u.username, u.role, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id"
                       " WHERE s.token_hash = ? AND s.expires_at > ?", (h, now)).fetchone()
    if row is not None and row["expires_at"] < now + SESSION_TTL - DAY:
        conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (now + SESSION_TTL, h))
        conn.commit()
    return row


def drop_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    conn.commit()


def drop_sessions(conn, user_id: int, keep: str | None = None) -> None:
    """Supprime les sessions de l'utilisateur, sauf celle du jeton `keep`."""
    conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                 (user_id, _token_hash(keep) if keep else ""))
    conn.commit()


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL, path="/", httponly=True, secure=True, samesite="lax")


class LoginLimiter:
    """5 échecs dans une fenêtre de 15 min → clé bloquée 15 min."""
    # ponytail: en mémoire, remis à zéro au redémarrage ; passer en table SQLite si plusieurs processus.
    MAX_FAILS = 5
    WINDOW = 15 * 60

    def __init__(self):
        self._fails: dict[str, list[float]] = {}
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def blocked(self, key: str, now: float) -> bool:
        with self._lock:
            return self._until.get(key, 0.0) > now

    def fail(self, key: str, now: float) -> None:
        with self._lock:
            # ponytail: purge O(n) à chaque échec ; n est borné par le nombre d'échecs sur 15 min
            self._fails = {k: v for k, v in self._fails.items() if v[-1] > now - self.WINDOW}
            self._until = {k: t for k, t in self._until.items() if t > now}
            fails = [t for t in self._fails.get(key, []) if t > now - self.WINDOW] + [now]
            if len(fails) >= self.MAX_FAILS:
                self._until[key] = now + self.WINDOW
                self._fails.pop(key, None)
            else:
                self._fails[key] = fails

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._until.pop(key, None)
