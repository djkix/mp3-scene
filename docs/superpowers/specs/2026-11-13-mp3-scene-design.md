# Mp3 Scene — Cahier des charges

Date : 13/11/2026 · Statut : à valider

Les points marqués **[choix]** sont des décisions prises par le rédacteur, pas des réponses du demandeur : à corriger si elles ne conviennent pas.

## 1. Intention

Une collection de plus de 100 000 releases MP3 « scene » dort sur un NAS, rangée en dossiers de release (`Artiste-Titre-(CAT)-WEB-2015-GRP`) contenant MP3, NFO, SFV et M3U. Aujourd'hui elle n'est consultable que par l'explorateur de fichiers du NAS.

L'objectif est un site web privé, dans l'esprit de 0daymusic.org, qui présente la collection **par release** (et non par artiste/album comme les lecteurs classiques) et permet de l'écouter en un clic, depuis un ordinateur ou un téléphone, à la maison comme à l'extérieur, y compris en castant sur un Chromecast.

## 2. Périmètre

### Objectifs

- Parcourir la collection : derniers ajouts, arborescence des dossiers, recherche plein texte, filtres genre / année.
- Un clic sur une release la charge dans un lecteur fixe en bas de page et démarre la lecture.
- Lecteur avec file d'attente, aléatoire, répétition, favoris et cast Chromecast.
- Afficher pour chaque release : informations extraites du nom, tags ID3 des pistes, contenu du NFO.
- Télécharger une piste, ou une release entière en zip.
- Accès par identifiant / mot de passe, avec gestion des utilisateurs par un administrateur.
- Installable en PWA sur Android et iOS.
- Livré en une image Docker.

### Hors périmètre

- Pochettes, forme d'onde.
- Écoute hors-ligne.
- Playlists, historique d'écoute, reprise de lecture entre appareils.
- AirPlay dédié, Sonos, DLNA (le Bluetooth est géré par le téléphone, rien à développer).
- Transcodage : les MP3 sont servis tels quels.
- Scan automatique planifié : le scan est lancé à la main.
- Édition de tags, vérification SFV, suppression ou déplacement de fichiers.
- Interface multilingue : français uniquement.

### Anti-objectifs

- Écrire quoi que ce soit sur le NAS : le partage est monté en lecture seule et l'appli ne tente jamais d'y écrire.
- Réorganiser la collection par tags ID3 : le dossier de release reste l'unité de base.
- Servir un fichier sans authentification, ou un fichier situé hors de la bibliothèque.

## 3. Contraintes

- **Hébergement** : conteneur Docker sur une machine distincte du NAS ; la bibliothèque est un partage **NFS** monté en lecture seule.
- **Accès** : depuis le réseau local et depuis Internet, derrière le reverse proxy HTTPS existant (domaine et certificat déjà en place). L'appli écoute en HTTP simple derrière le proxy.
- **Volume** : plus de 100 000 releases, soit de l'ordre du million de fichiers. L'interface ne lit jamais le NAS pour afficher une liste : tout passe par un index local.
- **Arborescence** : profondeur variable selon les catégories (parfois par lettre, parfois autrement). Aucune hypothèse sur le nombre de niveaux.
- **Tout le trafic passe par le reverse proxy en HTTPS**, y compris depuis le réseau local : le conteneur n'est pas joint directement. (Le cookie de session, la PWA et l'anti-force brute en dépendent.)
- Le reverse proxy n'ajoute **aucune barrière d'accès** (ni authentification, ni filtrage IP) : l'authentification est entièrement celle de l'appli, et le Chromecast peut joindre les URL signées.
- Aucun échantillon réel de l'arborescence n'est fourni : les règles de détection des releases et de découpage des noms suivent les conventions scene habituelles et seront ajustées après le premier scan réel.
- **Appareils** : Android, iPhone/iPad et ordinateur à parts égales.
- **Cast** : le bouton Chromecast n'existe que dans Chrome/Edge (Android et ordinateur). Il est masqué ailleurs, notamment sur iPhone, où c'est une limite de la plateforme.

## 4. Approches envisagées

| Approche | Avantages | Inconvénients |
|---|---|---|
| **Python (FastAPI) + SQLite + interface monopage sans build** — retenue | Un seul conteneur, peu de dépendances, recherche plein texte intégrée à SQLite (FTS5), suffisant pour ce volume | Interface écrite à la main, sans framework |
| Node.js + React + SQLite | JavaScript de bout en bout, écosystème de composants | Étape de build, davantage de dépendances à maintenir, aucun gain fonctionnel |
| Logiciel existant (Navidrome) | Rien à développer | Range par tags ID3 et non par release, pas de NFO, ne ressemble pas à 0daymusic |

Le demandeur a choisi la première.

## 5. Architecture

Un conteneur unique :

- **Serveur** : Python 3.12+, FastAPI, uvicorn. Sert l'API JSON, les fichiers audio et l'interface statique.
- **Index** : SQLite (mode WAL) dans un volume Docker dédié, avec table FTS5 pour la recherche. **[choix]**
- **Tags ID3** : bibliothèque `mutagen`. **[choix]**
- **Interface** : application monopage en HTML/CSS/JavaScript natif (modules ES, pas d'étape de build). Monopage obligatoire : le lecteur ne doit jamais être interrompu par un changement de page. **[choix]**
- **Bibliothèque** : volume NFS monté en lecture seule sur `/music`.

```
Navigateur / PWA ──HTTPS──> reverse proxy existant ──HTTP──> conteneur mp3-scene
                                                              ├─ /data  (SQLite, volume local)
Chromecast ──HTTPS (URL signée)──> reverse proxy ────────────┤
                                                              └─ /music (NFS, lecture seule)
```

## 6. Index et scan

### Qu'est-ce qu'une release

**[choix]** Un dossier qui contient directement au moins un fichier `.mp3`. Exception multi-disques : les sous-dossiers nommés `CD1`, `CD2`, `Disc1`, `Disk2`… (insensible à la casse) sont fusionnés dans le dossier parent, qui forme une seule release dont les pistes sont ordonnées par disque puis par nom de fichier.

Les sous-dossiers sans MP3 (`Covers`, `Proof`…) sont ignorés. Un dossier qui contient à la fois des MP3 et des sous-dossiers de release donne une release pour lui-même et une par sous-dossier.

La **catégorie** d'une release est le nom du dossier de premier niveau sous la racine (`01.Singles`, etc.).

### Données enregistrées

- **Release** : chemin relatif, nom du dossier, catégorie, date de modification du dossier, taille totale, nombre de pistes, présence d'un NFO, et les champs extraits du nom (ci-dessous). Genre et durée totale une fois les tags lus.
- **Piste** : release, nom de fichier, taille, numéro de disque ; puis titre, artiste, durée, bitrate, genre (ID3).
- **Utilisateur** : identifiant, mot de passe haché, rôle (`admin` / `utilisateur`).
- **Favori** : utilisateur, release ou piste, date.

### Extraction depuis le nom de release

Au mieux, sans jamais bloquer : le nom brut est toujours affiché et indexé pour la recherche.

- **Groupe** : dernier segment après le dernier `-`.
- **Année** : dernier segment de 4 chiffres entre 1950 et l'année courante.
- **Source** : segment reconnu parmi une liste (`WEB`, `Vinyl`, `CDM`, `CDS`, `CD`, `Promo`, `Bootleg`, `SAT`, `DAB`, `Cable`, `Tape`…).
- **Artiste** : texte avant le premier séparateur `--` ou `_-_` s'il y en a un, sinon avant le premier `-` ; `_` remplacés par des espaces.
- **Titre** : le reste, entre l'artiste et les segments ci-dessus.

Un nom qui ne suit pas le schéma garde ces champs vides.

Le découpage artiste / titre par le nom est ambigu par nature (`A-Trak-Tuna_Melt-…` donnerait l'artiste « A »). **[choix]** Dès que les tags ID3 sont lus, l'artiste affiché est celui des tags si toutes les pistes ont le même ; le découpage par le nom ne sert que d'ici là, ou à défaut de tags. Le filtre et la recherche ne dépendent pas de ce découpage.

### Scan en deux phases

Le scan est déclenché **uniquement à la main** par un administrateur (bouton dans l'écran d'administration). Un seul scan à la fois. L'interface reste utilisable pendant le scan.

1. **Phase rapide — structure.** Parcours de l'arborescence, détection des releases, noms de fichiers, tailles, dates, extraction depuis le nom. Les releases apparaissent dans l'interface dès qu'elles sont trouvées, lisibles immédiatement (la lecture n'a pas besoin des tags).
2. **Phase lente — tags ID3.** En tâche de fond, lecture des tags de chaque piste pas encore lue. Interruptible : un redémarrage du conteneur reprend où elle s'était arrêtée.

Le scan est **incrémental** : une release déjà connue dont la date de modification du dossier n'a pas changé n'est pas relue. **Dossiers déplacés ou renommés en amont** **[choix]** : une release disparue de son chemin, dont le nom de dossier se retrouve à un seul nouvel emplacement, est considérée comme déplacée. Elle garde son identité, donc ses favoris, sa date d'ajout et ses tags déjà lus (une réorganisation du NAS ne relance pas des heures de lecture de tags). Les releases réellement disparues sont retirées de l'index et des favoris.

Garde-fou : si la racine `/music` est vide ou inaccessible (montage NFS tombé), le scan s'arrête en erreur **sans rien retirer** de l'index.

L'écran d'administration montre l'état du scan : phase en cours, nombre de releases trouvées, pistes restant à lire, date et résultat du dernier scan, erreurs.

Conséquences à connaître :

- Le premier scan des tags sur environ un million de fichiers en NFS prendra des heures. Tant qu'il n'est pas terminé, genre, durée et bitrate manquent sur les releases non encore lues, et le filtre par genre est incomplet.
- **Date d'ajout** **[choix]** : pour les releases trouvées par le tout premier scan, c'est la date de modification du dossier sur le NAS. Pour celles découvertes par un scan ultérieur, c'est la date de ce scan, car beaucoup d'outils de copie conservent la date d'origine des dossiers et enterreraient les nouveautés. Dans l'explorateur du NAS, beaucoup de dossiers existants portent la même date (02/10/2022, date d'une copie) : les « derniers ajouts » ne sont vraiment pertinents que pour ce qui arrive après le premier scan.
- Le **genre** d'une release est le tag genre de sa première piste. **[choix]**
- L'**année** utilisée par le filtre est celle extraite du nom de release.

## 7. Écrans

Français uniquement. Thème clair et sombre, suivant le réglage de l'appareil. Mise en page adaptée au téléphone comme à l'ordinateur.

Structure commune : barre du haut (nom du site, champ de recherche, navigation), contenu, lecteur fixe en bas.

```
┌──────────────────────────────────────────────────────────────────┐
│ Mp3 Scene   [ Rechercher…          ]  Derniers  Dossiers  ★  ⚙  │
├──────────────────────────────────────────────────────────────────┤
│ Catégorie ▾   Genre ▾   Année ▾                                  │
│                                                                  │
│ 20/04/2015  Singles  A-Trak--Ibanez-(SP983)-WEB-2015-WUS         │
│             House · 2 pistes · 21 Mo            [+file] [★] [i]  │
│ 09/12/2014  Singles  A-Trak_feat_Andrew_Wyatt_-_Push-(FGR112BP)… │
│             Electro · 4 pistes · 38 Mo          [+file] [★] [i]  │
│ …                                                                │
├──────────────────────────────────────────────────────────────────┤
│ ⏮ ▶ ⏭  🔀 🔁   Titre de la piste        ───●────── 1:12 / 5:40   │
│                 Nom de la release        🔊 ──●──  [file] [cast] │
└──────────────────────────────────────────────────────────────────┘
```

Sur téléphone, chaque release tient sur deux lignes et le lecteur se réduit à : lecture/pause, suivant, titre, cast ; un appui l'agrandit pour montrer le reste.

### Liste de releases (composant commun)

Utilisé par les derniers ajouts, les dossiers, la recherche et les favoris. Chaque ligne montre : date, catégorie, nom de release, genre, nombre de pistes, taille.

- **Clic sur la ligne** : remplace la file d'attente par les pistes de la release et démarre la lecture.
- **Ajouter à la file** : ajoute les pistes à la fin, sans interrompre la lecture.
- **Favori** : ajoute / retire.
- **Détail** : ouvre la fiche de la release.

Les listes sont paginées ou chargées au défilement ; jamais plus d'une centaine de lignes demandées à la fois.

### Derniers ajouts (accueil)

Toutes les releases, de la plus récente à la plus ancienne (date du dossier). Filtres cumulables : catégorie, genre, année.

### Dossiers

Navigation dans l'arborescence telle qu'elle est sur le NAS, avec fil d'Ariane. Un dossier intermédiaire s'ouvre ; un dossier de release se comporte comme une ligne de la liste commune. Tri alphabétique.

### Recherche

Recherche plein texte sur le nom de release, où `_`, `-`, `.` et les parenthèses comptent comme des séparateurs de mots. Tous les mots saisis doivent être présents ; le dernier mot est recherché par préfixe (résultats pendant la frappe). Les filtres catégorie / genre / année s'appliquent aussi aux résultats.

### Fiche de release

- Nom brut, puis artiste, titre, source, année, groupe, catégorie, genre, taille, durée totale.
- Pistes : numéro, titre et artiste (ID3, ou nom de fichier à défaut), durée, bitrate. Clic sur une piste : lit la release à partir de cette piste. Par piste : favori, télécharger.
- Boutons : lire, ajouter à la file, favori, télécharger en zip.
- **NFO** : affiché en police à chasse fixe, décodé en CP437 pour respecter l'art ASCII, avec défilement horizontal plutôt que retour à la ligne. Lu à la demande sur le NAS, non indexé.

### Favoris

Deux onglets : releases et pistes. Propres à chaque utilisateur.

### File d'attente

Panneau ouvert depuis le lecteur : liste des pistes, piste en cours mise en évidence, clic pour sauter à une piste, retrait d'une piste, vidage. Pas de réorganisation par glisser-déposer. **[choix]**

### Connexion, compte, administration

- **Connexion** : identifiant, mot de passe.
- **Mon compte** : changer son mot de passe, se déconnecter.
- **Administration** (rôle admin) : liste des utilisateurs, création, suppression, réinitialisation de mot de passe, changement de rôle ; lancement et suivi du scan. Le dernier administrateur ne peut être ni supprimé ni rétrogradé.

## 8. Lecteur

- Commandes : lecture/pause, précédent, suivant, barre de progression cliquable, temps écoulé / durée, volume, aléatoire, répétition (désactivée / toute la file / la piste), file d'attente, cast.
- Affiche le titre de la piste et le nom de la release. Ni pochette ni forme d'onde.
- Enchaîne automatiquement sur la piste suivante de la file.
- La file, la piste en cours et les réglages (volume, aléatoire, répétition) sont conservés dans le navigateur : ils survivent à un rechargement de la page, mais ne se synchronisent pas entre appareils. Au rechargement, la lecture ne redémarre pas toute seule.
- **Commandes système** (API Media Session) : titre affiché et boutons lecture / pause / précédent / suivant sur l'écran verrouillé, dans les notifications, et sur les casques et enceintes Bluetooth. La lecture continue écran éteint, sur Android comme sur iOS.
- Le flux audio est le fichier MP3 d'origine, servi avec prise en charge des requêtes partielles (`Range`) pour permettre le déplacement dans la piste.

### Cast Chromecast

- Bouton cast affiché seulement quand le navigateur le permet (Chrome/Edge sur Android et ordinateur).
- Récepteur par défaut de Google (« Default Media Receiver ») : aucune appli à déclarer chez Google. **[choix]**
- Toute la file d'attente est transmise au Chromecast, qui enchaîne les pistes lui-même : la musique continue si le téléphone se verrouille ou quitte l'appli.
- Pendant le cast, le lecteur du site pilote le Chromecast (lecture/pause, précédent/suivant, position, volume) et reflète son état. À la déconnexion, la lecture reprend localement à la même position, en pause.
- Le Chromecast télécharge les fichiers lui-même, sans le cookie de session : l'appli lui fournit des **URL signées temporaires** (voir Sécurité). Ces URL utilisent l'adresse publique du site, que le Chromecast doit pouvoir joindre en HTTPS avec un certificat valide.

## 9. Authentification et sécurité

- Mots de passe hachés (argon2 ou bcrypt), jamais stockés ni journalisés en clair.
- Session par cookie `HttpOnly`, `Secure`, `SameSite=Lax`, valable 30 jours et prolongée à l'usage, pour ne pas redemander le mot de passe sans cesse dans la PWA. **[choix]**
- Toutes les routes exigent une session, sauf la page de connexion, les fichiers statiques de l'interface et les URL signées.
- **Compte administrateur initial** créé au premier démarrage à partir de variables d'environnement, uniquement si aucun utilisateur n'existe.
- **Anti-force brute** : après 5 échecs de connexion pour un même identifiant ou une même adresse IP, blocage de 15 minutes. L'appli fait confiance à l'en-tête `X-Forwarded-For` du reverse proxy pour connaître l'adresse du client.
- **URL signées pour le cast** : jeton HMAC lié à une piste, avec expiration (12 heures **[choix]**, pour couvrir une longue file). Un jeton ne donne accès qu'à cette piste, en lecture.
- **Accès aux fichiers** : toujours par identifiant de l'index, jamais par un chemin fourni par le client. Le chemin résolu est vérifié comme situé sous `/music` avant toute lecture.
- Les actions de modification (favoris, utilisateurs, scan) sont protégées contre les requêtes intersites (CSRF).
- Suppression d'un utilisateur ou changement de son mot de passe : ses sessions sont invalidées.

## 10. Téléchargements

- **Piste** : le fichier MP3 d'origine, sous son nom d'origine.
- **Release en zip** : archive générée à la volée, sans compression (les MP3 ne se compressent pas) et sans fichier temporaire, contenant tous les fichiers du dossier (MP3, NFO, SFV, M3U…) dans un dossier portant le nom de la release.

## 11. PWA

- Manifeste (nom, icônes, affichage plein écran, couleurs de thème) et service worker pour rendre l'appli installable sur Android et iOS.
- Le service worker ne met en cache que l'interface (pour un démarrage rapide), jamais l'audio ni les données. Sans connexion, l'appli affiche un message « hors ligne ».
- Une nouvelle version de l'interface est prise en compte au lancement suivant.

## 12. Déploiement

Livrables : `Dockerfile`, `docker-compose.yml` d'exemple, `README` en français (installation, montage NFS, configuration du reverse proxy, premier scan).

Le `docker-compose.yml` d'exemple déclare :

- le volume NFS de la bibliothèque, monté en lecture seule sur `/music` ;
- un volume local pour `/data` (base SQLite) ;
- le port HTTP exposé au reverse proxy.

Configuration par variables d'environnement :

| Variable | Rôle |
|---|---|
| `ADMIN_USER`, `ADMIN_PASSWORD` | Compte administrateur créé au premier démarrage |
| `SECRET_KEY` | Signature des sessions et des URL de cast |
| `PUBLIC_URL` | Adresse publique HTTPS du site, utilisée pour les URL envoyées au Chromecast |
| `TZ` | Fuseau horaire pour l'affichage des dates |

Le reverse proxy doit laisser passer les requêtes `Range` et ne pas mettre en tampon les réponses longues (flux audio, zip).

La sauvegarde se limite au volume `/data`. Le perdre oblige à refaire un scan et fait perdre comptes et favoris ; la musique n'est pas touchée.

## 13. Critères d'acceptation

1. Sur une bibliothèque de plus de 100 000 releases, toute liste, tout filtre et toute recherche répondent en moins d'une seconde.
2. Un clic sur une release démarre la lecture en moins de deux secondes sur le réseau local ; la navigation dans le site n'interrompt jamais la lecture.
3. Les releases trouvées par la phase rapide du scan sont visibles et lisibles avant la fin de la lecture des tags ; un redémarrage du conteneur pendant la phase lente ne perd pas le travail fait.
4. Un second scan sans changement sur le NAS ne relit aucun tag.
5. Un scan lancé alors que le montage NFS est tombé ne retire rien de l'index.
6. Depuis Chrome Android, une file de plusieurs pistes castée sur un Chromecast s'enchaîne jusqu'au bout téléphone verrouillé.
7. Sur iPhone et Android, la PWA installée continue la lecture écran éteint, avec les commandes sur l'écran verrouillé.
8. Sans session valide, aucune donnée ni aucun fichier n'est accessible ; une URL signée expirée ou modifiée est refusée ; aucun chemin hors de `/music` ne peut être lu.
9. Aucune écriture n'est tentée sur `/music`.
10. Le zip d'une release contient exactement les fichiers du dossier et s'ouvre sans erreur.
11. Un administrateur peut créer un utilisateur, qui se connecte et gère ses propres favoris, invisibles des autres.

Tests automatisés attendus au minimum sur : l'extraction depuis le nom de release, la détection des releases (dont multi-disques), le scan incrémental et son garde-fou, les contrôles d'accès (session, URL signée, chemin).

## 14. Laissé au développeur

- Schéma exact des tables et des index, forme précise des routes de l'API.
- Organisation du code et des fichiers de l'interface.
- Mécanisme de la tâche de fond du scan (thread, processus), tant que les critères 3 à 5 sont tenus.
- Choix entre pagination et chargement au défilement.
- Détail visuel (couleurs, typographie, icônes), dans l'esprit sobre de 0daymusic.org et de la capture du lecteur fournie.
- Liste complète des sources reconnues dans les noms de release.
