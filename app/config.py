import os
from dataclasses import dataclass, field
from pathlib import Path


MIN_SECRET = 32
# réseaux d'où X-Forwarded-For est cru par défaut : boucle locale et réseaux privés (pas le CGNAT 100.64.0.0/10)
TRUSTED_DEFAULT = ("127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")


@dataclass
class Settings:
    music_root: Path
    data_dir: Path
    secret_key: str
    public_url: str = ""
    admin_user: str | None = None
    admin_password: str | None = None
    backup_dir: Path | None = None   # dossier des sauvegardes (NAS monté) ; None : sauvegarde désactivée
    backup_hour: int = 3             # heure du serveur à partir de laquelle la sauvegarde du jour est faite
    discogs_token: str | None = None  # jeton personnel Discogs (pochettes des singles et maxis) ; None : Deezer et iTunes seuls
    stack_dir: Path = Path("/stack")
    # serveur Navidrome (API Subsonic) parcouru dans l'onglet Navidrome ; sans adresse, l'onglet n'apparaît pas
    # dossiers de musique supplémentaires : nom de dossier racine (« 05.Web Albums ») -> chemin dans le conteneur
    extra_roots: dict = field(default_factory=dict)
    # dossiers supplémentaires rangés avec les albums ou les singles (« >albums », « >singles ») : nom -> genre
    extra_kinds: dict = field(default_factory=dict)
    navidrome_url: str = ""
    navidrome_user: str = ""
    navidrome_password: str = ""
    # réseaux d'où X-Forwarded-For est cru (le reverse proxy) ; par défaut la boucle locale et les réseaux privés
    trusted_proxies: tuple = TRUSTED_DEFAULT  # dossier de la pile (compose, .env), monté en lecture seule s'il est à copier


    @property
    def roots(self):
        from .security import Roots
        return Roots(self.music_root, self.extra_roots)


def _extra(value: str) -> tuple[dict, dict]:
    """MUSIC_EXTRA : « Nom=/chemin;Nom 2=/chemin2>albums » -> ({nom: chemin}, {nom: « albums » | « singles »}). Le nom
    devient un dossier racine de la bibliothèque ; « >albums » ou « >singles » range ses releases avec les albums ou
    les singles au lieu d'en faire une catégorie à part."""
    roots, kinds = {}, {}
    for item in value.split(";"):
        name, sep, path = item.partition("=")
        path, _, kind = path.partition(">")
        name, path, kind = name.strip(), path.strip(), kind.strip().lower()
        if not sep or not name or not path or "/" in name or kind not in ("", "albums", "singles"):
            if item.strip():
                raise RuntimeError(f"MUSIC_EXTRA : « {item.strip()} » n'a pas la forme Nom=/chemin, Nom=/chemin>albums ou Nom=/chemin>singles.")
            continue
        roots[name] = Path(path)
        if kind:
            kinds[name] = kind
    return roots, kinds


def load() -> Settings:
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("La variable d'environnement SECRET_KEY est obligatoire.")
    if len(secret) < MIN_SECRET:  # la valeur n'apparaît jamais dans le message
        raise RuntimeError(f"La variable d'environnement SECRET_KEY doit contenir au moins {MIN_SECRET} caractères ; "
                           "générez-en une avec : python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    extra = _extra(os.environ.get("MUSIC_EXTRA", ""))
    return Settings(
        music_root=Path(os.environ.get("MUSIC_ROOT", "/music")),
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        secret_key=secret,
        public_url=os.environ.get("PUBLIC_URL", "").rstrip("/"),
        admin_user=os.environ.get("ADMIN_USER") or None,
        admin_password=os.environ.get("ADMIN_PASSWORD") or None,
        backup_dir=Path(os.environ["BACKUP_DIR"]) if os.environ.get("BACKUP_DIR") else None,
        backup_hour=min(23, max(0, int(os.environ.get("BACKUP_HOUR") or 3))),
        stack_dir=Path(os.environ.get("STACK_DIR", "/stack")),
        discogs_token=os.environ.get("DISCOGS_TOKEN") or None,
        extra_roots=extra[0], extra_kinds=extra[1],
        navidrome_url=os.environ.get("NAVIDROME_URL", "").rstrip("/"),
        navidrome_user=os.environ.get("NAVIDROME_USER", ""),
        navidrome_password=os.environ.get("NAVIDROME_PASSWORD", ""),
        **({"trusted_proxies": tuple(x.strip() for x in os.environ["TRUSTED_PROXIES"].split(",") if x.strip())}
           if os.environ.get("TRUSTED_PROXIES") else {}),
    )
