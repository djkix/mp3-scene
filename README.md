<div align="center">

# 🎧 Mp3 Scene

**Collection de releases MP3 « scene » — bibliothèque · lecteur web · Chromecast · PWA**

[![Version](https://img.shields.io/badge/version-1.20.0-purple?style=for-the-badge)](CHANGELOG.md)
[![Stack](https://img.shields.io/badge/stack-FastAPI_·_SQLite_·_JavaScript_pur-blue?style=for-the-badge)](#stack-technique)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)

*Parcourir et écouter des dizaines de milliers de releases stockées sur un NAS, depuis le navigateur ou le téléphone. Auto-hébergée, la musique n'est jamais modifiée.*

<br />

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Mp3 Scene  🔍 Rechercher une release…  Derniers Dossiers Explorer Favoris…│
├──────────────────────────────────────────────────────────────────────────┤
│              [ Localisations ▾ ] [ Genres ▾ ] [ Années ▾ ]               │
│ Nom                               Genre   Date        Pistes   Poids     │
│ VA-Compilation_Ete-2CD-2026-GRP   House   26/05/2026      52  934 Mo + ♡ │
│ Artiste-Titre-SINGLE-WEB-2026-GRP House   29/06/2026       1   11 Mo + ♥ │
│ Artiste-Essential_Mix-SAT-2025-…  Techno  25/09/2025       1  224 Mo + ♡ │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ Titre de la piste           ⇄  ⏮  ▶  ⏭  ↻                   🔊  ☰  ⎚   │
│ Nom-De-La-Release     1:36 ━━━━━━━●────────── 55:36                      │
└──────────────────────────────────────────────────────────────────────────┘
```

<br />

[Fonctionnalités](#fonctionnalités) ·
[Architecture](#architecture) ·
[Installation](#installation) ·
[Dockge](#installation-via-dockge) ·
[Reverse proxy](#reverse-proxy) ·
[Variables d'environnement](#variables-denvironnement) ·
[Historique](#historique-des-versions)

</div>

---

## Vue d'ensemble

**Mp3 Scene** transforme un dossier de releases MP3 sur un NAS en bibliothèque consultable et écoutable.
Le partage est monté **en lecture seule** : l'application n'écrit que dans son dossier `data/` (une base SQLite).
Tout est déduit des dossiers et des fichiers, sans rien saisir.

| Écran | Rôle |
|-------|------|
| **Derniers** | Releases par date d'ajout, filtres catégorie, genre et année, recherche plein texte |
| **Dossiers** | Navigation dans l'arborescence du NAS |
| **Fiche** | Pochette, pistes, durées, débit, NFO, téléchargement en zip |
| **Favoris** | Releases et pistes favorites, **playlists**, **releases hors ligne**, **historique** et **statistiques d'écoute**, par compte |
| **Explorer** | Groupes, artistes et genres : nombre de releases et poids ; recherche par release ou par piste |
| **Compte** | Changement de mot de passe, langue (français ou anglais) ; pour un administrateur, aussi : utilisateurs, scan de la bibliothèque, version installée |

| Déduit automatiquement | D'où ça vient |
|------------------------|---------------|
| **Localisation** | Dossier de premier niveau du partage |
| **Artiste, titre, année, source, groupe** | Nom du dossier de la release |
| **Genre, durée, artiste de la piste** | Tags ID3, lus en tâche de fond |

---

## Fonctionnalités

### 📚 Bibliothèque
- Liste en colonnes : **vignette de pochette, nom, genre, date, pistes, poids, localisation**, avec libellés ; sur téléphone, le nom puis une ligne de détails
- Colonnes **triables** d'un clic sur leur titre (bureau)
- Filtres **Localisations**, **Genres**, **Années** et recherche plein texte (SQLite FTS5)
- Défilement infini par pages de 50, navigation par dossiers
- Fiche de release : **pochette**, pistes par disque, NFO affiché, **téléchargement en zip** à la volée

### 🎵 Lecteur
- Barre de lecture en pied de page : pochette, titre sur deux lignes, lecture, précédent, suivant, **aléatoire**, **répétition**
- **Forme d'onde** en guise de barre de progression, calculée à la première écoute puis gardée en base
- **File d'attente** modifiable, ajout d'une release entière d'un clic
- Volume **vertical** au survol, coupure du son, molette
- Raccourcis clavier : Espace (lecture/pause), ← → (± 5 s), Échap
- Commandes sur l'écran verrouillé et le casque (Media Session)

### 📱 Deux interfaces
- **Bureau** : barre en trois colonnes, tableau large
- **Téléphone** : onglets en bas, à portée de pouce ; lecteur réduit, puis **plein écran** au toucher du titre ; cibles de 44 px
- Thème clair ou sombre selon le système
- Interface en **français ou en anglais**, selon le navigateur ou au choix sur la page Compte

### 📺 Chromecast
- Envoi de la file au Chromecast depuis Chrome ou Edge (Android et ordinateur)
- Liens signés valables 12 heures, sans session
- Pochette de la release affichée sur l'écran

### 🔎 Scan
- **Manuel**, lancé depuis la page Compte (administrateurs) ; incrémental : un second scan ne relit que ce qui a changé
- Deux phases : structure (détection des releases), puis tags ID3 en tâche de fond
- Reprise après redémarrage ; dossiers illisibles et noms non UTF-8 ignorés et signalés

### 🛡️ Comptes et administration
- Comptes **administrateur** et **utilisateur**, mots de passe hachés (argon2)
- Session par cookie de 30 jours, anti-force brute (5 échecs → 15 minutes)
- **Numéro de version** dans la page Compte et **bandeau** quand une version plus récente est publiée (administrateurs seulement)

### 📲 PWA
- Installable sur Android et iPhone ; la coquille de l'interface est en cache, jamais la musique

---

## Architecture

```
Navigateur / PWA ──HTTPS──▶ Reverse proxy ──HTTP──▶ mp3-scene (FastAPI, port 8000)
                                                      │            │
Chromecast ──HTTPS /cast/ (URL signées)──▶            │            │
                                              /data (SQLite)   /music (NAS, lecture seule)
```

- **Un seul conteneur** : API, fichiers statiques et flux audio.
- **SQLite** dans `data/` : index, comptes, sessions, favoris. Rien d'autre à sauvegarder.
- **Interface sans étape de build** : modules JavaScript servis tels quels.
- Les MP3 sont servis tels quels, avec `Range` ; aucun transcodage.

---

## Stack technique

| Couche | Technologies |
|--------|--------------|
| Backend | Python 3.12, FastAPI, Starlette, Uvicorn |
| Base de données | SQLite (WAL, FTS5) |
| Audio et images | mutagen (tags ID3), flux HTTP avec `Range`, mpg123 (formes d'onde), Pillow (vignettes) |
| Sécurité | argon2-cffi, cookie de session, URL de cast signées |
| Frontend | JavaScript pur (modules ES), CSS, service worker, Google Cast SDK |
| Tests | pytest (serveur), `node --test` (interface) |
| CI/CD | GitHub Actions, GHCR (`ghcr.io/djkix/mp3-scene`) |
| Orchestration | Docker Compose, compatible **Dockge** |

---

## Installation

### Prérequis

- Une machine avec Docker et Docker Compose v2, **distincte du NAS**, qui accède au partage en NFS.
- Le **client NFS** sur la machine Docker : `sudo apt install nfs-common` (Debian/Ubuntu) ou `sudo dnf install nfs-utils` (Fedora/RHEL).
- Un NAS qui exporte le dossier des releases en NFS.
- Un reverse proxy HTTPS (domaine et certificat valide) devant l'application.

### Côté NAS : export NFS en lecture seule

Sur Synology (DSM) — les chemins de menus ci-dessous sont écrits de mémoire et peuvent varier selon la version de DSM :

1. Panneau de configuration → Services de fichiers → NFS : activer NFS, version maximale NFSv4.1 (ou 4).
2. Panneau de configuration → Dossier partagé → sélectionner le dossier des releases → Modifier → onglet **Autorisations NFS** → Créer.
3. Adresse IP du serveur Docker (ou son sous-réseau), privilège **Lecture seule**, Squash : **Mapper tous les utilisateurs sur admin** (`all_squash`) ou « Aucun mappage » si l'UID 1000 a déjà le droit de lire, « Activer l'accès asynchrone » sans importance.
4. Noter le « Chemin de montage » affiché en bas de la fenêtre (par ex. `/volume1/Releases`) : c'est le `device` du compose.

L'appli tourne dans le conteneur sous l'UID/GID **1000:1000** (modifiables à la construction : `--build-arg UID=… --build-arg GID=…`).
Cet utilisateur doit pouvoir **lire** tous les dossiers et fichiers de l'export. Avec `all_squash`, c'est le compte
vers lequel le NAS ramène tout le monde qui compte, pas l'UID 1000 ; sans squash, les permissions Unix du NAS
s'appliquent à l'UID 1000. Un dossier illisible est ignoré par le scan, signalé dans les journaux et par un
avertissement sur la page Compte (voir « Première connexion et premier scan »).

Les dossiers système de Synology (`#recycle`, `@eaDir`) présents sous l'export apparaissent comme des catégories :
pour les exclure, exportez un sous-dossier propre qui ne contient que les releases.

### Installation via Dockge

L'image est publiée sur GHCR : rien à construire sur le serveur.

1. Dans Dockge, créer un stack `mp3-scene` et y coller ce `compose.yaml` :

```yaml
services:
  mp3-scene:
    image: ghcr.io/djkix/mp3-scene:latest
    container_name: mp3-scene
    restart: unless-stopped
    environment:
      SECRET_KEY: ${SECRET_KEY:?renseignez SECRET_KEY dans .env}
      ADMIN_USER: ${ADMIN_USER:-admin}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-}
      PUBLIC_URL: https://mp3.exemple.fr
      TZ: Europe/Paris
    ports:
      - 127.0.0.1:8000:8000
    volumes:
      - /mnt/media/releases:/music:ro
      - ./data:/data
```

2. Dans la zone `.env` du stack :

```bash
SECRET_KEY=        # python3 -c "import secrets; print(secrets.token_urlsafe(48))"
ADMIN_USER=admin
ADMIN_PASSWORD=    # 8 caractères au moins ; à retirer après le premier démarrage
```

3. Adapter trois lignes :
   - `PUBLIC_URL` : l'adresse publique HTTPS du site, sans slash final. Elle sert aux URL envoyées au Chromecast.
   - `ports` : `127.0.0.1` si le proxy est sur la même machine ; sinon l'adresse LAN de la machine Docker. Ne jamais publier ce port sur Internet : les ports publiés par Docker contournent en général ufw/firewalld.
   - le volume `/music` : le dossier où la machine Docker monte le partage du NAS (ici `/mnt/media/releases`).
4. Créer le dossier de données avec le bon propriétaire, sinon Docker le crée en root : `mkdir -p data && sudo chown 1000:1000 data` dans le dossier du stack.
5. Cliquer sur **Déployer**. L'état doit passer à « healthy ».

Le compte administrateur est créé au premier démarrage, uniquement s'il n'existe encore aucun utilisateur.
Vérifier que la bibliothèque est bien en lecture seule : `docker compose exec mp3-scene touch /music/x` doit échouer.

### Sans Dockge

```bash
git clone https://github.com/djkix/mp3-scene.git && cd mp3-scene
cp .env.example .env && nano .env        # SECRET_KEY, ADMIN_USER, ADMIN_PASSWORD
mkdir -p data && sudo chown 1000:1000 data
nano docker-compose.yml                  # PUBLIC_URL, ports, adresse et chemin NFS du NAS
docker compose up -d
docker compose logs -t -f mp3-scene
```

Le `docker-compose.yml` du dépôt monte le partage lui-même, par un volume NFS (`<IP_NAS>` et `device`).
Si vous changez ces valeurs plus tard, le volume nommé garde l'ancienne définition : `docker compose down`,
`docker volume rm mp3-scene_music`, puis `docker compose up -d`.

### Mettre à jour

Dans Dockge : **Mettre à jour** (télécharge la dernière image et recrée le conteneur). En ligne de commande :

```bash
docker compose pull && docker compose up -d
```

Une nouvelle version est annoncée par un bandeau dans l'application (administrateurs). Pour rester sur une version
précise, remplacer `latest` par son numéro : `ghcr.io/djkix/mp3-scene:1.1.0`.

---

## Reverse proxy

Exigences, quel que soit le proxy :

- **HTTPS** obligatoire, y compris depuis le réseau local (cookie de session `Secure`, PWA, cast). Tout le trafic passe par le proxy.
- Transmettre l'en-tête **`Range`** (lecture et déplacement dans les pistes) sans le retirer.
- **Pas de mise en tampon** des réponses pour `/api/tracks/`, `/api/releases/*/zip`, `/cast/` et `/s/` (flux audio et zip à la volée).
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

---

## Première connexion et premier scan

1. Ouvrir `https://mp3.exemple.fr`, se connecter avec `ADMIN_USER` / `ADMIN_PASSWORD`, puis **changer le mot de passe** (page Compte).
2. Page **Administration → Lancer le scan**. Le scan est **manuel** : il n'y a pas de scan planifié, relancez-le quand la collection change.
3. La phase « structure » (détection des releases) parcourt tous les dossiers : sur une très grande bibliothèque en NFS, elle peut elle aussi être longue. Le compteur « Releases trouvées » progresse et les releases apparaissent par lots dans la liste, mais la vue par dossiers ne se remplit qu'à la fin de cette phase. Si le conteneur est arrêté pendant cette phase, la page Compte l'indique : relancez le scan.
4. La phase « tags » (lecture des durées, genres, artistes ID3) peut durer **plusieurs heures** sur 100 000 releases et plus en NFS. Pendant toute cette phase (donc parfois des heures au premier scan), le bouton « Lancer le scan » reste désactivé et aucun nouveau scan n'est possible. Le filtre par genre et les durées se complètent progressivement ; un redémarrage du conteneur ne perd pas le travail déjà fait, et un second scan sans changement ne relit aucun tag.
5. Suivre un scan : `docker compose logs -t -f mp3-scene` (début du scan, fin de chaque phase avec ses chiffres, erreurs).
6. Si le scan a ignoré quelque chose, il se termine normalement mais la page Compte affiche un **avertissement** (par ex. « 3 dossier(s) illisible(s) et 2 nom(s) non UTF-8 ignorés — voir les journaux ») et les journaux donnent les chemins :
   - `dossier illisible ignoré` : l'appli n'a pas le droit de lire ce dossier ; vérifier les permissions NFS et le squash sur le NAS (voir plus haut). Les releases déjà indexées dessous sont conservées.
   - `nom non UTF-8 ignoré` : nom de fichier ou de dossier qui n'est pas de l'UTF-8 valide (SQLite ne peut pas le stocker) ; le renommer sur le NAS, puis relancer un scan.
7. Un scan lancé alors que le montage NFS est tombé, ou sur une racine qui ne contient aucune des releases déjà indexées (mauvais export, dossiers système seuls), échoue sans rien retirer de l'index.

## Installer l'application (PWA)

- **Android** (Chrome) : menu ⋮ → **Installer l'application**.
- **iPhone / iPad** (Safari) : bouton Partager → **Sur l'écran d'accueil**.

La coquille de l'interface est mise en cache pour démarrer vite ; la musique et les données ne le sont jamais. Sans connexion, l'appli affiche « Vous êtes hors ligne ». Une nouvelle version est prise en compte au lancement suivant.

## Chromecast

- Uniquement dans **Chrome ou Edge** sur Android et ordinateur. Impossible depuis un iPhone (limite de la plateforme) : le bouton est masqué ailleurs.
- Le Chromecast doit pouvoir joindre `PUBLIC_URL` en **HTTPS avec un certificat valide**, sans barrière d'accès au niveau du proxy.
- Les liens envoyés au Chromecast sont valables **12 heures**.
- La file est envoyée au Chromecast par fenêtres d'au plus 100 pistes. Au-delà, la fenêtre suivante n'est envoyée que tant que la page ou l'appli reste ouverte sur le téléphone.

## Sécurité

- Session par cookie valable 30 jours, prolongée à l'usage.
- 5 échecs de connexion pour un même identifiant ou une même adresse IP : blocage 15 minutes. Conséquence : quiconque connaît un identifiant peut tenir ce compte bloqué, 15 minutes à la fois, en ratant 5 connexions. Choisissez un `ADMIN_USER` peu devinable (pas `admin`) et gardez un second compte administrateur.
- Changer le mot de passe administrateur après la première connexion ; `ADMIN_PASSWORD` n'est lu qu'à la création du premier compte, retirez-le de `.env` après le premier démarrage (le compose n'en a plus besoin ; d'ici là il est en clair dans `.env` et dans l'environnement du conteneur), puis `docker compose up -d`.
- Changer `SECRET_KEY` invalide toutes les sessions, tous les liens de cast et tous les liens de partage en cours.
- **Liens de partage** (`/s/…`) : tout utilisateur connecté peut en créer pour une release ou pour l'une de ses playlists. Ils donnent accès, sans compte, aux seules pistes partagées, pendant 7 jours. Leur auteur peut les révoquer depuis la page Compte.
- `.env` contient des secrets : il est ignoré par git, ne le publiez pas.

## Sauvegarde

Sauvegardez uniquement `./data` (base SQLite : comptes, favoris, index ; le sous-dossier `thumbs/` des vignettes peut être exclu, il se reconstruit). Sans elle, il faut refaire un scan complet et les comptes et favoris sont perdus ; la musique n'est pas touchée. Pour une copie cohérente : `docker compose stop mp3-scene`, copier `data/`, `docker compose start mp3-scene`.

Vider réellement l'index (le scan refuse de retirer toutes les releases d'un coup) : `docker compose stop mp3-scene`, supprimer `data/mp3scene.db*`, `docker compose start mp3-scene`, puis relancer un scan. **Tout** est perdu : index, comptes (l'administrateur est recréé depuis `ADMIN_USER` / `ADMIN_PASSWORD`, à remettre dans `.env`) et favoris de tous les utilisateurs.

Une base créée par une version plus récente de l'appli est refusée au démarrage (message dans les journaux) : revenir à cette version, ou restaurer une sauvegarde de `data/`.

---

## Variables d'environnement

| Variable | Obligatoire | Rôle |
|----------|-------------|------|
| `SECRET_KEY` | oui | Signe les sessions et les liens de cast ; 32 caractères au moins. La changer invalide toutes les sessions |
| `ADMIN_USER` | non (`admin`) | Identifiant du premier compte administrateur |
| `ADMIN_PASSWORD` | au premier démarrage | Mot de passe du premier compte, 8 caractères au moins ; lu seulement tant qu'aucun compte n'existe |
| `PUBLIC_URL` | pour le cast | Adresse publique HTTPS, sans slash final |
| `TZ` | non | Fuseau des journaux du serveur |
| `MUSIC_ROOT` | non (`/music`) | Dossier des releases dans le conteneur |
| `DATA_DIR` | non (`/data`) | Dossier de la base SQLite |

---

## Développement

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                       # tests Python
node --test static/js/                    # tests JavaScript
python3 scripts/make_demo_library.py /tmp/demo-music     # fausse bibliothèque
mkdir -p /tmp/demo-data
MUSIC_ROOT=/tmp/demo-music DATA_DIR=/tmp/demo-data SECRET_KEY=dev-dev-dev-dev-dev-dev-dev-dev-32 ADMIN_USER=admin ADMIN_PASSWORD=adminadmin \
  PUBLIC_URL=http://localhost:8000 .venv/bin/uvicorn --factory app.main:create_app --port 8000
python3 scripts/make_icons.py             # régénère les icônes PWA
docker build -t mp3-scene .               # image locale
```

En local, utilisez `http://localhost` (les navigateurs y acceptent le cookie `Secure`).
Si vous modifiez un fichier de `static/`, incrémentez `VERSION` dans `static/sw.js` et gardez sa liste `PRECACHE` à jour (un test le vérifie).
Les dépendances Python sont figées (`==`) : une reconstruction installe exactement les versions testées.

### Publier une version

Une version = une étiquette `vX.Y.Z` poussée sur `main`. GitHub Actions construit alors l'image
(`X.Y.Z` et `latest`) puis crée la publication GitHub, que l'application consulte pour afficher le bandeau.

```bash
git tag v1.2.0 && git push origin v1.2.0
```

---

## Limites connues

- Pochette absente du Chromecast. Une vignette déjà créée n'est pas refaite si l'image change sur le NAS (supprimer `data/thumbs/` pour tout refaire). Forme d'onde calculée à la première écoute seulement (une piste à la fois).
- Pas d'écoute hors ligne.
- Pas de playlists ni de reprise entre appareils.
- Pas d'AirPlay dédié, de Sonos ni de DLNA (le Bluetooth est géré par le téléphone).
- Pas de transcodage : les MP3 sont servis tels quels.
- Scan manuel uniquement, pas de scan planifié.
- Pas d'édition de tags, de vérification SFV, ni de suppression ou déplacement de fichiers.
- Interface en français et en anglais uniquement ; la page « hors ligne » reste en français.
- Cast : Chrome/Edge uniquement, pas depuis un iPhone.

---

## Historique des versions

Le détail est dans le [journal des modifications](CHANGELOG.md).

### 1.20.0 — 18 novembre 2026

**Polices et icônes** des maquettes, **choix du thème**, **piste en cours** mise en évidence, **radio persistante**.

### 1.19.0 — 18 novembre 2026

**Nouvel habillage**, en clair et en sombre.

### 1.18.0 — 17 novembre 2026

**Radio** : une file sans fin de pistes proches, depuis une release ou une piste.

### 1.17.0 — 17 novembre 2026

**Releases similaires** sur la fiche et contrôle qualité **« sans pochette »**.

### 1.16.0 — 16 novembre 2026

**Enchaînement sans blanc** et fondu, **égaliseur**, liens de partage **révocables**, **tableau de bord** et **contrôle qualité** de la bibliothèque.

### 1.15.0 — 16 novembre 2026

File et playlists **réordonnables**, **mix aléatoire**, pastille **nouveau**, **liens de partage** (7 jours), **minuterie de sommeil**, raccourcis clavier.

### 1.14.0 — 16 novembre 2026

**Écoute hors ligne** (releases gardées sur l'appareil) et **reprise de la lecture sur un autre appareil**.

### 1.13.0 — 16 novembre 2026

**Playlists**, **recherche par piste**, **statistiques d'écoute**, pages **Artistes** et **Genres** (entrée Explorer), liens depuis la fiche release.

### 1.12.1 — 16 novembre 2026

**Fiche release** : pistes en « artiste - titre », colonne Genre, colonnes centrées.

### 1.12.0 — 16 novembre 2026

**Page Groupes** : nombre de releases et poids total par groupe, releases d'un groupe filtrables par genre et année.

### 1.11.0 — 16 novembre 2026

**Dix minutes d'avance** : les pistes suivantes sont gardées en mémoire, et une coupure de réseau ne fait plus sauter de piste.

### 1.10.1 — 16 novembre 2026

**Pistes favorites et historique** : libellés de colonnes, plus de place pour l'artiste, release sur deux lignes au besoin.

### 1.10.0 — 16 novembre 2026

**Colonne Débit** (débit moyen des pistes, triable) dans les listes ; colonnes Genre, Date, Pistes et Débit centrées.

### 1.9.1 — 15 novembre 2026

**Lecteur** : « Artiste - Titre », et plus de cadre vert au clic sur la forme d'onde.

### 1.9.0 — 15 novembre 2026

**Admin fusionné dans Compte** : un seul onglet ; les sections d'administration n'apparaissent que pour un administrateur.

### 1.8.0 — 15 novembre 2026

**Balayage dans le lecteur plein écran** sur téléphone : vers la gauche, piste suivante ; vers la droite, précédente.

### 1.7.1 — 14 novembre 2026

**Pochette sur le Chromecast** : l'écran affiche la pochette de la release en cours.

### 1.7.0 — 14 novembre 2026

**Vignettes de pochette dans les listes**, créées à la première demande et gardées dans `data/thumbs/`.

### 1.6.0 — 14 novembre 2026

**Forme d'onde.** La barre de progression du lecteur devient la forme d'onde de la piste, calculée à la première
écoute puis gardée en base.

### 1.5.0 — 14 novembre 2026

**Pochettes.** Sur la fiche, dans le lecteur et sur l'écran verrouillé, depuis l'image du dossier ou celle des tags.

### 1.4.1 — 14 novembre 2026

**NFO centré et lisible sur téléphone**, sans défilement horizontal. « Catégorie » devient « Localisation ».

### 1.4.0 — 14 novembre 2026

**Historique d'écoute et interface en anglais.** Historique par compte dans un onglet de la page Favoris ;
interface en français ou en anglais selon le navigateur, au choix sur la page Compte.

### 1.3.0 — 14 novembre 2026

**Colonnes triables.** Un clic sur un titre de colonne trie toute la liste, un second inverse l'ordre. Colonne Nom
élargie, titres de colonnes centrés.

### 1.2.0 — 14 novembre 2026

**Adresse lisible des fiches.** L'adresse d'une fiche porte le nom de la release au lieu d'un numéro ; les anciens
liens fonctionnent toujours. Licence MIT ajoutée.

### 1.1.0 — 14 novembre 2026

**Liste en colonnes.** Nom, genre, date, pistes, poids et localisation ont chacun leur colonne, avec un libellé
en tête ; les filtres portent leur nom (Catégories, Genres, Années) et sont centrés. Sur téléphone, le nom reste
en première ligne, les détails en dessous. README refait, journal des modifications ajouté.

### 1.0.0 — 14 novembre 2026

**Première version publiée.** Bibliothèque, recherche, dossiers, fiche de release, favoris, lecteur avec file
d'attente, Chromecast, PWA, comptes et administration. Interface en deux mises en page, bureau et téléphone,
lecteur repensé avec volume vertical. Image publiée sur GHCR, numéro de version dans la page Admin et bandeau
de nouvelle version.

---

## Licence

[MIT](LICENSE)
