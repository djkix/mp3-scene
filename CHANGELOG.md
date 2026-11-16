# Journal des modifications

Toutes les modifications notables de Mp3 Scene sont consignées ici, la plus récente en premier.
Le projet suit le [versionnage sémantique](https://semver.org/lang/fr/). Ce journal est repris dans le
[README](README.md#historique-des-versions).

## [1.11.0](https://github.com/djkix/mp3-scene/compare/v1.10.1...v1.11.0) (2026-11-16)

### Résumé

**Dix minutes d'avance pour les coupures de réseau.** Pendant la lecture, le lecteur télécharge en mémoire les
pistes suivantes jusqu'à disposer d'environ dix minutes d'audio d'avance : une coupure dans les transports ne
s'entend plus. Si le réseau manque quand même, la piste n'est plus sautée : le lecteur affiche « Connexion perdue »
et reprend seul, au même endroit, au retour de la connexion. Rien n'est téléchargé tant que la lecture est en pause,
ni pendant un cast. La piste lancée à la main reste lue en flux : l'avance vaut à partir de la piste suivante.

## [1.10.1](https://github.com/djkix/mp3-scene/compare/v1.10.0...v1.10.1) (2026-11-16)

### Résumé

**Pistes favorites et historique plus lisibles.** La liste a des libellés de colonnes (Date ou Durée, Artiste,
Titre, Release), l'artiste dispose de plus de place, et l'artiste comme la release passent à la ligne au lieu
d'être coupés. Sur téléphone, chaque piste s'affiche sur quatre lignes : titre, artiste, release, date.

## [1.10.0](https://github.com/djkix/mp3-scene/compare/v1.9.1...v1.10.0) (2026-11-16)

### Résumé

**Colonne Débit dans les listes, colonnes centrées.** Chaque release affiche le débit moyen de ses pistes (en
kbit/s), entre Pistes et Poids ; la colonne est triable. Les colonnes Genre, Date, Pistes et Débit sont centrées.
Le débit vient des tags déjà lus : aucune migration, aucun scan.

## [1.9.1](https://github.com/djkix/mp3-scene/compare/v1.9.0...v1.9.1) (2026-11-15)

### Résumé

**Lecteur : artiste devant le titre, plus de cadre au clic sur l'onde.** Le lecteur affiche « Artiste - Titre »
quand les tags donnent les deux. Le cadre vert autour de la forme d'onde n'apparaît plus au clic ; il reste au
clavier, pour repérer le focus.

## [1.9.0](https://github.com/djkix/mp3-scene/compare/v1.8.0...v1.9.0) (2026-11-15)

### Résumé

**Admin fusionné dans Compte.** L'onglet Admin disparaît : pour un administrateur, la page Compte contient aussi les
utilisateurs, le scan de la bibliothèque et la version. Un utilisateur simple garde la page Compte seule.
L'ancienne adresse `#/admin` renvoie vers Compte. Aucune migration, aucun scan.

## [1.8.0](https://github.com/djkix/mp3-scene/compare/v1.7.1...v1.8.0) (2026-11-15)

### Résumé

**Balayage dans le lecteur plein écran.** Sur téléphone, un balayage vers la gauche passe à la piste suivante, vers
la droite revient à la précédente (ou au début de la piste après 3 secondes d'écoute, comme le bouton). Un geste
court, vertical, ou parti de la forme d'onde ou de la file d'attente est ignoré. Aucune migration, aucun scan.

## [1.7.1](https://github.com/djkix/mp3-scene/compare/v1.7.0...v1.7.1) (2026-11-14)

### Résumé

**Pochette sur le Chromecast.** Pendant une diffusion, l'écran affiche la pochette de la release en cours. L'image
est servie par un lien signé, comme la piste (`/cast/<piste>/cover`, valable 12 heures, sans session). Aucune
migration, aucun scan.

## [1.7.0](https://github.com/djkix/mp3-scene/compare/v1.6.1...v1.7.0) (2026-11-14)

### Résumé

**Vignettes de pochette dans les listes.** Chaque ligne de release affiche sa pochette en vignette, sur bureau
comme sur téléphone ; une release sans pochette garde un emplacement vide, pour que les noms restent alignés. La
vignette est créée à la première demande puis gardée dans `data/thumbs/` (environ 5 Ko par release), y compris
le fait qu'une release n'a pas de pochette. Nouvelle dépendance : Pillow. Aucune migration, aucun scan.

### Fonctionnalités

* vignettes de pochette dans les listes Derniers, Recherche, Dossiers et Favoris

### Correctifs

* filtre « Localisations » affiché en entier sur téléphone

## [1.6.1](https://github.com/djkix/mp3-scene/compare/v1.6.0...v1.6.1) (2026-11-14)

### Résumé

**Forme d'onde plus lisible.** Le relief est accentué à l'affichage : sur les musiques très compressées, dont le
niveau varie peu, la forme d'onde ressemblait à un bloc presque plein. Les données calculées ne changent pas.

### Correctifs

* relief de la forme d'onde accentué

## [1.6.0](https://github.com/djkix/mp3-scene/compare/v1.5.0...v1.6.0) (2026-11-14)

### Résumé

**Forme d'onde.** Dans le lecteur, la barre de progression devient la forme d'onde de la piste : la partie écoutée
est colorée, un clic ou un glissement déplace la lecture. Elle est calculée par le serveur à la première écoute
d'une piste (quelques secondes, jusqu'à une minute pour un mix de deux heures), puis gardée en base ; en attendant,
le curseur habituel reste affiché. L'image embarque le décodeur `mpg123`. Nouvelle table `waveforms`, créée au
démarrage ; aucune action à la mise à jour.

### Fonctionnalités

* forme d'onde dans la barre de progression du lecteur, bureau et téléphone

## [1.5.0](https://github.com/djkix/mp3-scene/compare/v1.4.1...v1.5.0) (2026-11-14)

### Résumé

**Pochettes.** La pochette d'une release s'affiche sur sa fiche (un clic l'ouvre en grand), dans le lecteur —
vignette sur bureau et dans le lecteur réduit, grande image dans le lecteur plein écran du téléphone — et sur
l'écran verrouillé. Elle vient de l'image du dossier (« front », « cover » ou « folder » de préférence), sinon de
l'image incluse dans les tags de la première piste. Sans image, rien ne s'affiche. Aucune migration, aucun scan.

### Fonctionnalités

* pochette sur la fiche, dans le lecteur et sur l'écran verrouillé

### Tests

* vérification de la syntaxe de tous les fichiers de l'interface

## [1.4.1](https://github.com/djkix/mp3-scene/compare/v1.4.0...v1.4.1) (2026-11-14)

### Résumé

**NFO centré et lisible sur téléphone.** Le bloc NFO est centré sous la fiche ; quand il est plus large que
l'écran, sa police est réduite pour que toute la largeur soit visible sans défilement horizontal. « Catégorie »
devient « Localisation » sur la fiche et dans les filtres, comme dans la liste. Aucune migration.

### Correctifs

* NFO centré, ajusté à la largeur de l'écran
* libellé « Localisation » à la place de « Catégorie »

## [1.4.0](https://github.com/djkix/mp3-scene/compare/v1.3.0...v1.4.0) (2026-11-14)

### Résumé

**Historique d'écoute et interface en anglais.** Chaque piste lancée est notée dans un historique propre à chaque
compte, affiché dans un nouvel onglet de la page Favoris et effaçable. L'interface existe en français et en
anglais : elle suit la langue du navigateur, avec un choix sur la page Compte et sur la page de connexion.
Nouvelle table `plays`, créée au démarrage ; aucune action à la mise à jour.

### Fonctionnalités

* historique d'écoute par compte (lecture locale et Chromecast), onglet Historique, effacement
* interface en français et en anglais, messages d'erreur du serveur compris

## [1.3.0](https://github.com/djkix/mp3-scene/compare/v1.2.0...v1.3.0) (2026-11-14)

### Résumé

**Colonnes triables.** Un clic sur un titre de colonne trie la liste (nom, genre, date, pistes, poids,
localisation), un second inverse l'ordre ; le tri est fait par le serveur, sur toute la bibliothèque. La colonne
du nom gagne de la place sur celle du genre, et les titres de colonnes sont centrés. Aucune migration.

### Fonctionnalités

* tri par colonne dans les listes Derniers, Recherche, Dossiers et Favoris (bureau)
* colonne Nom élargie, titres de colonnes centrés

## [1.2.0](https://github.com/djkix/mp3-scene/compare/v1.1.0...v1.2.0) (2026-11-14)

### Résumé

**Adresse lisible des fiches.** L'adresse d'une fiche porte le nom de la release
(`#/release/VA-Compilation-2CD-2026-GRP`) au lieu d'un numéro. Les anciens liens numérotés fonctionnent toujours.
Licence MIT ajoutée. Aucune migration.

### Fonctionnalités

* adresse de fiche par nom de release ; les liens par numéro restent acceptés

### Documentation

* licence MIT, descriptif du site pour maquette (`docs/brief-design.md`)

## [1.1.0](https://github.com/djkix/mp3-scene/compare/v1.0.0...v1.1.0) (2026-11-14)

### Résumé

**Liste en colonnes.** La liste des releases passe en colonnes séparées, dans l'ordre nom, genre, date, pistes,
poids, localisation, puis les actions, avec un libellé en tête de chaque colonne. Les filtres affichent leur nom
(Catégories, Genres, Années), ont la même largeur et sont centrés. Aucune migration.

### Fonctionnalités

* liste des releases en colonnes libellées ; sur téléphone, nom puis ligne de détails
* filtres libellés et centrés

### Documentation

* README refait sur le modèle des autres projets, journal des modifications ajouté
* `docker-compose.yml` : image `ghcr.io/djkix/mp3-scene` au lieu d'une construction locale

## [1.0.0](https://github.com/djkix/mp3-scene/releases/tag/v1.0.0) (2026-11-14)

### Résumé

**Première version publiée.** Application complète : scan d'un partage NAS en lecture seule, bibliothèque,
lecteur, Chromecast, PWA, comptes. Image Docker publiée sur GHCR à chaque version.

### Fonctionnalités

* scan de structure incrémental et lecture des tags ID3 en tâche de fond
* extraction des champs depuis le nom de release
* authentification, comptes administrateur et utilisateur, anti-force brute
* API bibliothèque : listes, recherche plein texte, dossiers, fiche, favoris
* flux audio avec `Range`, téléchargement en zip, URL signées pour le cast
* interface : connexion, listes, recherche, dossiers, fiche, favoris, compte, administration
* lecteur : file d'attente, aléatoire, répétition, Media Session
* Chromecast : file transmise au récepteur par fenêtres de 100 pistes
* PWA installable
* interface bureau et téléphone, lecteur repensé, volume vertical
* numéro de version dans la page Admin et bandeau de nouvelle version

### Correctifs

* noms non UTF-8 ignorés au lieu de faire échouer le scan
* aucune écriture SQLite pendant les accès NFS ; déplacement fiable après un scan interrompu
* limiteur de connexions atomique ; une connexion réussie ne consomme pas le quota de l'adresse IP
* `ADMIN_PASSWORD` facultatif après le premier démarrage
