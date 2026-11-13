# Mp3 Scene

Application web auto-hébergée pour parcourir et écouter une collection privée de releases MP3 « scene » stockée sur un NAS.
Backend FastAPI + SQLite, interface en JavaScript pur (aucune étape de build), lecteur intégré, cast Chromecast, installable en PWA.
La musique n'est jamais modifiée : le partage est monté en lecture seule, l'appli n'écrit que dans son dossier `data/`.

## Prérequis

- Une machine avec Docker et Docker Compose v2, **distincte du NAS**, qui monte le partage en NFS.
- Un NAS qui exporte le dossier des releases en NFS (v4).
- Un reverse proxy HTTPS (domaine + certificat valide) devant l'appli.

## Côté NAS : export NFS en lecture seule

Sur Synology (DSM) :

1. Panneau de configuration → Services de fichiers → NFS : activer NFS, version maximale NFSv4.1 (ou 4).
2. Panneau de configuration → Dossier partagé → sélectionner le dossier des releases → Modifier → onglet **Autorisations NFS** → Créer.
3. Adresse IP du serveur Docker (ou son sous-réseau), privilège **Lecture seule**, Squash : **Mapper tous les utilisateurs sur admin** (`all_squash`) ou « Aucun mappage » si l'UID 1000 a déjà le droit de lire, « Activer l'accès asynchrone » sans importance.
4. Noter le « Chemin de montage » affiché en bas de la fenêtre (par ex. `/volume1/Releases`) : c'est le `device` du compose.

L'appli tourne dans le conteneur sous l'UID/GID **1000:1000** (modifiables à la construction : `--build-arg UID=… --build-arg GID=…`).
Cet utilisateur doit pouvoir **lire** tous les dossiers et fichiers de l'export. Avec `all_squash`, c'est le compte
vers lequel le NAS ramène tout le monde qui compte, pas l'UID 1000 ; sans squash, les permissions Unix du NAS
s'appliquent à l'UID 1000. Un dossier illisible est ignoré par le scan.

## Installation

> **Note de l'auteur :** le `Dockerfile` et le `docker-compose.yml` ont été écrits et relus sans Docker disponible sur la machine de développement. Ils n'ont **pas** été construits ni exécutés par l'auteur : votre premier `docker compose build` est le vrai test. Si une étape échoue, c'est un bug à signaler.

```bash
git clone <URL_DU_DEPOT> mp3-scene && cd mp3-scene
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # à coller dans SECRET_KEY
nano .env                                                       # SECRET_KEY, ADMIN_USER, ADMIN_PASSWORD
mkdir -p data && sudo chown 1000:1000 data                      # sinon Docker crée data/ en root et l'appli ne peut pas écrire
```

Éditer `docker-compose.yml` :

- `PUBLIC_URL` : l'adresse publique HTTPS du site, sans slash final (`https://mp3.exemple.fr`). Elle sert aux URL envoyées au Chromecast ; si elle est vide ou ne commence pas par `http`, le démarrage écrit un avertissement dans les journaux et le cast ne fonctionnera pas.
- `<IP_NAS>` et `device` (chemin de montage NFS du NAS) dans le volume `music`.
- `ports` : par défaut `127.0.0.1:8000:8000` (reverse proxy sur la même machine). Si le proxy est sur une autre machine, mettre l'adresse LAN de la machine Docker et filtrer au pare-feu ; ne jamais publier ce port sur Internet ni sur tout le réseau (voir plus bas).

```bash
docker compose up -d --build
docker compose logs -f mp3-scene      # démarrage, avertissements
docker compose ps                     # l'état doit passer à « healthy »
```

Le compte administrateur est créé au premier démarrage, uniquement s'il n'existe encore aucun utilisateur.
Vérifier que la bibliothèque est bien en lecture seule : `docker compose exec mp3-scene touch /music/x` doit échouer.

## Reverse proxy

Exigences, quel que soit le proxy :

- **HTTPS** obligatoire, y compris depuis le réseau local (cookie de session `Secure`, PWA, cast). Tout le trafic passe par le proxy.
- Transmettre l'en-tête **`Range`** (lecture et déplacement dans les pistes) sans le retirer.
- **Pas de mise en tampon** des réponses pour `/api/tracks/`, `/api/releases/*/zip` et `/cast/` (flux audio et zip à la volée).
- Transmettre **`X-Forwarded-For`** (et `X-Forwarded-Proto`). L'appli lit le dernier élément de `X-Forwarded-For` pour son anti-force brute.
- Délai de lecture long (≥ 1 h) pour les téléchargements de zip.
- Aucune authentification ni filtrage IP au niveau du proxy : le Chromecast doit atteindre les URL `/cast/` et l'appli gère elle-même les accès.
- Le port 8000 ne doit être joignable **que par le proxy**, et il doit y avoir **exactement un proxy** devant l'appli : avec deux proxys en cascade ou un port ouvert, l'anti-force brute verrait une mauvaise adresse IP (voire une adresse choisie par l'attaquant).

Nginx (extrait du bloc `server` HTTPS) :

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;      # écrase toute valeur fournie par le client
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Range $http_range;
    proxy_set_header If-Range $http_if_range;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    client_max_body_size 1m;
}
```

Synology DSM (Panneau de configuration → Portail de connexion → Avancé → Proxy inversé → Créer) :

- Source : HTTPS, nom d'hôte `mp3.exemple.fr`, port 443 ; destination : HTTP, adresse de la machine Docker, port 8000.
- DSM ajoute lui-même `X-Forwarded-For` et `X-Forwarded-Proto` ; aucun en-tête personnalisé n'est nécessaire.
- Onglet **Avancé** : délais de connexion, d'envoi et de lecture à 3600 s si l'option existe.
- Associer le certificat du domaine (Sécurité → Certificat → Configurer). Ne cocher aucune règle d'accès (pas d'authentification du portail).
- DSM ne propose pas de désactiver la mise en tampon : si la lecture ou les zips saccadent, utiliser Nginx directement.
- Le port 8000 de la machine Docker doit n'être joignable que depuis le DSM (pare-feu), donc `ports` du compose sur l'adresse LAN de la machine Docker.

## Première connexion et premier scan

1. Ouvrir `https://mp3.exemple.fr`, se connecter avec `ADMIN_USER` / `ADMIN_PASSWORD`, puis **changer le mot de passe** (page Compte).
2. Page **Administration → Lancer le scan**. Le scan est **manuel** : il n'y a pas de scan planifié, relancez-le quand la collection change.
3. La phase « structure » (détection des releases) est rapide : les releases deviennent visibles et lisibles au fur et à mesure.
4. La phase « tags » (lecture des durées, genres, artistes ID3) peut durer **plusieurs heures** sur 100 000 releases et plus en NFS. Le filtre par genre et les durées se complètent progressivement ; un redémarrage du conteneur ne perd pas le travail déjà fait, et un second scan sans changement ne relit aucun tag.
5. Les fichiers ou dossiers dont le nom n'est pas de l'UTF-8 valide sont **ignorés** (SQLite ne peut pas les stocker). Ils sont signalés dans les journaux :
   `docker compose logs mp3-scene | grep "non UTF-8"`. Corriger en renommant sur le NAS, puis relancer un scan.
6. Un scan lancé alors que le montage NFS est tombé ne retire rien de l'index.

## Installer l'application (PWA)

- **Android** (Chrome) : menu ⋮ → **Installer l'application**.
- **iPhone / iPad** (Safari) : bouton Partager → **Sur l'écran d'accueil**.

La coquille de l'interface est mise en cache pour démarrer vite ; la musique et les données ne le sont jamais. Sans connexion, l'appli affiche « Vous êtes hors ligne ». Une nouvelle version est prise en compte au lancement suivant.

## Chromecast

- Uniquement dans **Chrome ou Edge** sur Android et ordinateur. Impossible depuis un iPhone (limite de la plateforme) : le bouton est masqué ailleurs.
- Le Chromecast doit pouvoir joindre `PUBLIC_URL` en **HTTPS avec un certificat valide**, sans barrière d'accès au niveau du proxy.
- Les liens envoyés au Chromecast sont valables **12 heures**.
- Une file très longue peut ne pas se charger sur le récepteur.

## Sécurité

- Session par cookie valable 30 jours, prolongée à l'usage.
- 5 échecs de connexion pour un même identifiant ou une même adresse IP : blocage 15 minutes.
- Changer le mot de passe administrateur après la première connexion ; `ADMIN_PASSWORD` n'est lu qu'à la création du premier compte, vous pouvez ensuite le retirer de `.env`.
- Changer `SECRET_KEY` invalide toutes les sessions et tous les liens de cast en cours.
- `.env` contient des secrets : il est ignoré par git, ne le publiez pas.

## Sauvegarde

Sauvegardez uniquement `./data` (base SQLite : comptes, favoris, index). Sans elle, il faut refaire un scan complet et les comptes et favoris sont perdus ; la musique n'est pas touchée. Pour une copie cohérente : `docker compose stop mp3-scene`, copier `data/`, `docker compose start mp3-scene`.

## Mise à jour

```bash
git pull && docker compose up -d --build
```

## Développement

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                       # tests Python
node --test static/js/                    # tests JavaScript (Node 20+)
python3 scripts/make_demo_library.py /tmp/demo-music     # fausse bibliothèque
MUSIC_ROOT=/tmp/demo-music DATA_DIR=/tmp/demo-data SECRET_KEY=dev ADMIN_USER=admin ADMIN_PASSWORD=adminadmin \
  PUBLIC_URL=http://localhost:8000 .venv/bin/uvicorn --factory app.main:create_app --port 8000
python3 scripts/make_icons.py             # régénère les icônes PWA (bibliothèque standard seule)
```

(`mkdir -p /tmp/demo-data` au préalable.) En local, utilisez `http://localhost` (les navigateurs y acceptent le cookie `Secure`).
Si vous modifiez un fichier de `static/`, incrémentez `VERSION` dans `static/sw.js` et gardez sa liste `PRECACHE` à jour (un test le vérifie).

## Limites connues

- Pas de pochettes ni de forme d'onde.
- Pas d'écoute hors ligne.
- Pas de playlists, d'historique d'écoute ni de reprise entre appareils.
- Pas d'AirPlay dédié, de Sonos ni de DLNA (le Bluetooth est géré par le téléphone).
- Pas de transcodage : les MP3 sont servis tels quels.
- Scan manuel uniquement, pas de scan planifié.
- Pas d'édition de tags, de vérification SFV, ni de suppression ou déplacement de fichiers.
- Interface en français uniquement.
- Cast : Chrome/Edge uniquement, pas depuis un iPhone.
