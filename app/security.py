import hashlib
import secrets
import threading
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException

SESSION_TTL = 30 * 86400
DAY = 86400
COOKIE = "session"

_hasher = PasswordHasher()
# argon2 réserve ~64 Mio par calcul et /api/login est public : au plus 4 calculs simultanés, les autres attendent
_argon2_slots = threading.BoundedSemaphore(4)
# vérifié pour un identifiant inconnu, afin que la durée de réponse ne trahisse pas son existence
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(pw: str) -> str:
    with _argon2_slots:
        return _hasher.hash(pw)


def verify_password(hash: str, pw: str) -> bool:
    try:
        with _argon2_slots:
            return _hasher.verify(hash, pw)
    except (VerificationError, InvalidHashError):
        return False


def username_error(name: str) -> str | None:
    """Message d'erreur si le nom (déjà nettoyé des espaces) est invalide, sinon None."""
    if not 1 <= len(name) <= 64:
        return "Le nom d'utilisateur doit contenir entre 1 et 64 caractères."
    return None


def password_error(pw: str) -> str | None:
    if len(pw) < 8:
        return "Le mot de passe doit contenir au moins 8 caractères."
    return None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: int, now: float) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    conn.execute("INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?,?,?)",
                 (_token_hash(token), user_id, now + SESSION_TTL))
    conn.commit()
    return token


def session_user(conn, token: str, now: float) -> dict | None:
    """Utilisateur de la session (id, username, role, expires_at, renewed) ; renewed = échéance repoussée."""
    h = _token_hash(token)
    row = conn.execute("SELECT u.id, u.username, u.role, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id"
                       " WHERE s.token_hash = ? AND s.expires_at > ?", (h, now)).fetchone()
    if row is None:
        return None
    user = dict(row, renewed=row["expires_at"] < now + SESSION_TTL - DAY)
    if user["renewed"]:
        conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (now + SESSION_TTL, h))
        conn.commit()
    return user


def session_exists(conn, token: str, now: float) -> bool:
    return conn.execute("SELECT 1 FROM sessions WHERE token_hash = ? AND expires_at > ?",
                        (_token_hash(token), now)).fetchone() is not None


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
    """Au plus 5 essais par clé dans une fenêtre de 15 min ; le 5e bloque la clé 15 min."""
    # ponytail: en mémoire, remis à zéro au redémarrage ; passer en table SQLite si plusieurs processus.
    MAX_TRIES = 5
    WINDOW = 15 * 60

    def __init__(self):
        self._tries: dict[str, list[float]] = {}
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def blocked(self, key: str, now: float) -> bool:
        with self._lock:
            return self._until.get(key, 0.0) > now

    def attempt(self, keys, now: float) -> bool:
        """Réserve un essai pour toutes les clés, AVANT la vérification du mot de passe (atomique).

        False si l'une est bloquée : rien n'est alors compté ni prolongé."""
        with self._lock:
            # ponytail: purge O(n) à chaque essai ; n est borné par le nombre d'essais sur 15 min
            self._tries = {k: v for k, v in self._tries.items() if v and v[-1] > now - self.WINDOW}
            self._until = {k: t for k, t in self._until.items() if t > now}
            if any(k in self._until for k in keys):
                return False
            for k in keys:
                tries = [t for t in self._tries.get(k, []) if t > now - self.WINDOW] + [now]
                self._tries[k] = tries
                if len(tries) >= self.MAX_TRIES:
                    self._until[k] = now + self.WINDOW
            return True

    def forgive(self, key: str) -> None:
        """Retire un essai réservé (connexion réussie) sans effacer les échecs précédents."""
        with self._lock:
            tries = self._tries.get(key)
            if tries:
                tries.pop()
                if len(tries) < self.MAX_TRIES:
                    self._until.pop(key, None)

    def reset(self, key: str) -> None:
        with self._lock:
            self._tries.pop(key, None)
            self._until.pop(key, None)


def safe_path(root: Path, *parts: str) -> Path:
    """Chemin résolu (liens symboliques suivis) sous `root` et existant ; sinon 404."""
    root = root.resolve()
    try:
        p = root.joinpath(*parts).resolve()
    except (OSError, ValueError):
        raise HTTPException(404, "Fichier introuvable.") from None
    if not p.is_relative_to(root) or not p.exists():
        raise HTTPException(404, "Fichier introuvable.")
    return p
