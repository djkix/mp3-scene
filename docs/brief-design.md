# Mp3 Scene — descriptif pour maquette

Document destiné à un designer ou à un outil de maquettage. Il décrit le produit **tel qu'il fonctionne aujourd'hui
(version 1.52.0)** : à qui il sert, ses écrans, les données affichées, les états et les contraintes à respecter.
L'habillage visuel actuel est décrit à la fin ; il peut être remis en cause, les contraintes ne le peuvent pas.

> **Règle pour la maquette : ce document est la liste complète des fonctionnalités.** Ne rien ajouter qui n'y figure
> pas : aucun écran, bouton, onglet, réglage, donnée ou texte supplémentaire. La section 10 liste ce que
> l'application ne fait pas.

## 1. Le produit en bref

Mp3 Scene est une application web privée, auto-hébergée, pour **parcourir et écouter une collection de
releases MP3 « scene »** stockée sur un NAS. Une release est un dossier nommé selon une convention stricte,
par exemple `VA-Toolroom_Ibiza_2026-(TOOL142001Z)-WEB-2026-AOV`, qui contient de 1 à plus de 50 pistes.

- **Taille réelle** : environ 46 000 releases, de 10 Mo à 1 Go chacune.
- **Usage** : retrouver une release, la lancer, enchaîner, écouter longtemps (mixes d'une heure et plus), souvent
  dans les transports avec une connexion instable.
- **Appareils** : ordinateur (navigateur) et téléphone (application installée, PWA). Les deux comptent autant.
- **Langues** : français (par défaut) et anglais, au choix dans la page Compte. Maquettes en français.
- **Lecture seule** : l'application ne modifie jamais les fichiers de musique.

## 2. Utilisateurs

| Profil | Ce qu'il fait | Particularités |
|---|---|---|
| **Utilisateur** | Parcourt, cherche, écoute, met en favori, crée des playlists, garde hors ligne, partage, télécharge | Quelques proches du propriétaire |
| **Administrateur** | Tout cela, plus : comptes, scan de la bibliothèque, tableau de bord, contrôle qualité, version | Voit les sections d'administration dans Compte et le bandeau de nouvelle version |

Ce sont des connaisseurs : le **nom brut de la release est l'information principale**, il doit rester lisible
en entier, en police à chasse fixe, sans être tronqué.

## 3. Structure générale

Trois zones permanentes, une fois connecté :

1. **Barre du haut** : nom du site « Mp3 Scene » (lien vers l'accueil), champ de recherche « Rechercher une release… », navigation.
2. **Contenu** : l'écran courant.
3. **Lecteur** : fixé en bas, visible dès qu'une piste a été lancée, sur tous les écrans.

Navigation, cinq entrées : **Derniers** (accueil), **Catégories**, **Explorer**, **Favoris**, **Compte**. L'entrée active est marquée.

Deux **bandeaux** peuvent apparaître sous la barre du haut :
- pour les administrateurs : « Nouvelle version 1.19.0 disponible (installée : 1.18.0). Voir les nouveautés » ;
- pour tous, quand le serveur est injoignable : « Serveur injoignable : mode hors ligne. » avec un bouton « Réessayer »
  (voir 4.11).

## 4. Écrans

### 4.1 Connexion
- Titre « Mp3 Scene », champs **Identifiant** et **Mot de passe**, bouton **Se connecter**.
- Erreurs : « Identifiant ou mot de passe incorrect. » ; « Trop de tentatives échouées : compte bloqué 15 minutes. »
- Pas d'inscription, pas de mot de passe oublié (les comptes sont créés par un administrateur).

### 4.2 Derniers (accueil)
Liste des releases, la plus récente en premier.

- En tête, quand il y en a : « 12 nouvelles releases depuis votre dernière visite. » Ces releases portent une
  pastille **nouveau** avant leur nom.
- **Filtres**, centrés au-dessus de la liste : **Catégories**, **Genres**, **Années** (décennies puis années), **Sources** (listes déroulantes ;
  jusqu'à plusieurs dizaines de genres), suivis du bouton **Mix** (lit 50 pistes tirées au hasard parmi les releases
  qui passent les filtres).
- **Colonnes**, dans cet ordre, avec libellé en tête, séparées par de l'espace sans trait vertical. Un clic sur un
  libellé trie la liste, un second inverse l'ordre (▲ ▼ à côté du libellé actif) :

| Colonne | Exemple | Remarques |
|---|---|---|
| Vignette | pochette 40 px | Sans libellé ; vide s'il n'y a pas de pochette |
| Nom | `VA-Toolroom_Ibiza_2026-(TOOL142001Z)-WEB-2026-AOV` | Chasse fixe, peut passer sur deux lignes, jamais tronqué ; pastille « nouveau » éventuelle, avant le nom |
| Genre | House | Centré ; peut être vide tant que les tags ne sont pas lus |
| Date | 26/05/2026 | Centré ; date de sortie lue dans le NFO, sinon date d'ajout |
| Pistes | 52 | Centré |
| Débit | 320 kbit/s | Centré ; moyenne des pistes, vide tant que les tags ne sont pas lus |
| Poids | 934 Mo | Aligné à droite |
| Catégorie | Compilations | Dossier de premier niveau sous un nom court (Singles, Compilations, Live & Radio) ; info-bulle : nom du dossier |
| Actions | + ♡ › | Ajouter à la file, favori (plein quand actif), ouvrir la fiche |

- **Clic sur une ligne** : lance la lecture de la release. Les trois actions sont des cibles distinctes.
- Défilement infini (50 par page). Messages : « Chargement… », « Fin de la liste », « Aucun résultat »,
  erreur avec bouton « Réessayer ».

Cette **liste de releases** (colonnes, tri, actions, messages) est réutilisée telle quelle dans la recherche, les
dossiers, les pages de groupe et d'artiste, les favoris et le contrôle qualité.

### 4.3 Recherche
- Le champ de la barre du haut filtre au fil de la frappe. Deux onglets : **Releases** et **Pistes**.
- **Releases** : la liste de releases, avec les mêmes filtres (sans le bouton Mix).
- **Pistes** : les pistes dont le titre ou l'artiste contient les mots cherchés, dans la liste de pistes décrite en 4.7.
- Message : « Aucun résultat ».

### 4.4 Catégories
- **Fil d'Ariane** : Catégories › Compilations › -=Kontor=- (premier niveau : Singles, Compilations, Live & Radio ; les
  sous-dossiers gardent leur nom)
- Au premier niveau, le fil d'Ariane se termine par le lien **Toute la catégorie** (liste filtrée).
- Liste des **sous-dossiers**, puis la **liste des releases** du dossier qui sont de cette catégorie.
- Messages : « Dossier vide. », « Dossier introuvable. »

### 4.5 Explorer
- Trois **onglets** : **Groupes**, **Artistes**, **Genres**.
- Chaque onglet : un tableau **Nom**, **Releases** (nombre), **Poids** ; en-têtes cliquables pour trier ; au-dessus,
  un champ « Filtrer la liste… » et les sélecteurs **Genres** et **Années**, puis une rangée de lettres centrée
  (**Tous**, **#**, **A** à **Z** ; la lettre active est en vert) qui limite la liste à une initiale ; en bas, un total
  (« 1 240 lignes · 46 012 releases · 3,2 To »). Au plus 1000 lignes affichées, avec la mention « seules les 1000
  premières sont affichées : filtrez pour affiner. »
- **Page d'un groupe ou d'un artiste** : titre « Groupes › NOM » suivi du nombre de releases et du poids, puis la
  liste de releases avec ses filtres et le bouton Mix.
- **Page d'un artiste** : pour un administrateur, un bouton **Rattacher à…** après le titre (demande le nom de
  l'artiste cible) ; trois onglets sous le titre, **Releases** (les siennes), **Avec** (releases dont le nom
  l'associe à un autre artiste : feat, vs, &) et **Apparitions** (releases d'un autre artiste, compilations surtout,
  où il signe une piste).
- Un clic sur un **genre** ouvre la liste Derniers filtrée sur ce genre.

### 4.6 Fiche d'une release
- **Nom** de la release en titre.
- **Pochette** à gauche des informations (au-dessus sur téléphone), quand la release en a une ; un clic l'ouvre en grand.
- **Informations** (les champs absents ne s'affichent pas ; valeurs alignées à droite de leur colonne) : Artiste, Titre, Source (WEB, CD, VINYL, SAT…),
  Année, Date, Groupe, Catégorie, Genre, Taille, Durée. Artiste, Source, Année, Groupe et Genre sont des liens vers la liste
  correspondante.
- Pour un administrateur, le bouton **Corriger** (après le favori) ouvre une boîte : Artiste, Catégorie (liste),
  Genre, la mention « Un champ vidé revient à la valeur automatique… », **Enregistrer**, **Annuler**.
- **Actions**, dans cet ordre : **Lire** (principale), **Ajouter à la file**, **Radio**, **Ajouter à une playlist**,
  **Garder hors ligne** (devient « Téléchargement 3/12… » puis « Retirer du hors-ligne »), **Partager**,
  **Favori** (♡), **Télécharger (zip)**.
- **Radio** : lit la release, puis enchaîne sans fin des pistes proches (même artiste, ou même genre à deux ans près).
  Message « Radio lancée. ». Aucun écran ni réglage propre : les pistes arrivent dans la file d'attente. La radio reprend après un rechargement
  de la page ou sur un autre appareil.
- **Partager** : crée un lien public valable 7 jours et le copie (« Lien copié, valable 7 jours. »).
- **Tableau des pistes** : N°, Artiste - Titre (ou nom de fichier à défaut), Durée, Débit, Genre (colonnes centrées),
  puis trois actions par piste : **⋯** (plus d'actions, voir 4.9), **♡** favori, **⤓** téléchargement. Sur téléphone,
  Débit, Genre et téléchargement sont masqués. Séparateurs « CD 1 », « CD 2 » pour les releases multi-disques.
  Clic sur une piste : lecture à partir de cette piste. La **piste en cours** est mise en évidence (trait vert à
  gauche, titre en vert, ▶ à la place du numéro), ici comme dans les listes de pistes. Message : « Aucune piste. »
- **Autres versions** (si la release en a) : sous les pistes, avant le NFO, les releases de même artiste et de même titre, en lignes compactes.
- **Releases similaires** (si la release en a) : jusqu'à douze lignes compactes sous le NFO (sous les pistes s'il n'y en a pas) — vignette, nom,
  détails sur une seconde ligne, actions + ♡ › — même artiste d'abord, puis même genre et même année.
- **NFO** (si la release en a un) : bloc de texte en chasse fixe, art ASCII, centré ; sur téléphone la police est
  réduite pour que toute la largeur soit visible sans défilement horizontal.
- Erreur : « Release introuvable. Retour à la liste ».

### 4.7 Favoris
Six onglets : **Releases**, **Pistes**, **Playlists**, **Hors ligne**, **Historique**, **Statistiques**
(défilement horizontal des onglets sur téléphone).

- **Releases** : la liste de releases. Vide : « Aucune release favorite ».
- **Pistes** : **liste de pistes** — durée, artiste, titre, release d'origine (lien vers sa fiche), bouton ⋯, retrait
  du favori. Clic sur une ligne : lecture. Vide : « Aucune piste favorite ».
- **Playlists** : voir 4.8.
- **Hors ligne** : tableau Nom, Pistes, Poids des releases et playlists gardées sur l'appareil, avec « Retirer du
  hors-ligne » par ligne et le total « 1,4 Go sur cet appareil ». Vide : « Aucune release hors ligne : ouvrez une
  release et choisissez « Garder hors ligne ». » Navigateur incompatible : « Le stockage hors ligne n'est pas
  disponible dans ce navigateur. »
- **Historique** : liste de pistes avec la date d'écoute en première colonne, la plus récente en premier ; bouton
  « Effacer l'historique » (avec confirmation). Vide : « Aucune écoute ».
- **Statistiques** : sélecteur **Période** (7 derniers jours, 30 derniers jours, 12 derniers mois, Tout
  l'historique) ; total « 342 écoutes · 28,5 h de musique » ; quatre classements avec le nombre d'écoutes :
  **Pistes les plus écoutées**, **Artistes les plus écoutés**, **Genres les plus écoutés**, **Groupes les plus
  écoutés**. Vide : « Aucune écoute ».

### 4.8 Playlists (onglet de Favoris)
- **Liste** : champ « Nouvelle playlist » et bouton **Créer** ; tableau **Playlist**, **Pistes**, **Durée**, puis par
  ligne **Lire**, **Renommer** (✎), **Supprimer** (✕, avec confirmation). Vide : « Aucune playlist : créez-en une,
  puis ajoutez des pistes avec le bouton ♫. »
- **Contenu d'une playlist** : titre « Playlists › NOM » ; boutons **Lire** (principal), **Garder hors ligne**,
  **Partager** ; liste de pistes avec, par ligne, **▲ ▼** pour changer l'ordre et **✕** « Retirer de la playlist ».
  Vide : « Playlist vide ».
- Une piste figure au plus une fois par playlist. Les playlists sont propres à chaque utilisateur.

### 4.9 Boîtes de dialogue
- **Plus d'actions** (bouton ⋯ d'une piste) : **Lire ensuite**, **Ajouter à la file**, **Radio** ; puis « Ajouter à
  une playlist » : un bouton par playlist existante, champ « Nouvelle playlist » avec **Créer et ajouter** ; **Fermer**.
- **Ajouter à une playlist** (bouton ♫ ou bouton de la fiche, pour une release entière) : la même boîte sans les
  trois premières actions.
- **Réglages audio** : voir 5.
- Les confirmations (supprimer, révoquer, effacer) utilisent la boîte native du navigateur.

### 4.10 Compte
Dans cet ordre :
- **Identifiant** et **rôle** (utilisateur ou administrateur) affichés.
- **Changer le mot de passe** : mot de passe actuel, nouveau, confirmation, bouton, message de succès ou d'erreur
  (8 caractères au moins).
- **Langue** : liste déroulante Français / English.
- **Thème** : liste déroulante Système / Clair / Sombre.
- **Liens de partage** : tableau **Nom**, **Expire le**, **Ouvertures**, avec **Copier** et **Révoquer** (confirmation)
  par ligne. Vide : « Aucun lien de partage en cours. »
- **Administration** (administrateurs seulement) : bouton **Ouvrir l'administration** (voir 4.12).
- **Session** : bouton **Se déconnecter**.

### 4.11 Mode hors ligne
Quand le serveur est injoignable et que des releases sont gardées sur l'appareil, l'application n'affiche que le
bandeau « Serveur injoignable : mode hors ligne. » (bouton « Réessayer »), la liste des releases et playlists gardées
(celle de l'onglet Hors ligne) et le lecteur. Rien d'autre n'est accessible.

### 4.12 Administration (administrateurs)
Page ouverte depuis Compte. À gauche, une **navigation par type d'action** (colonne fixe à partir de 1100 px de
large, rangée défilante au-dessus du contenu en dessous) ; la section active est sur fond vert pâle :
**Vue d'ensemble** · *Bibliothèque* : **Scan**, **Contrôle qualité**, **Corrections** · *Classement* : **Règles** ·
*Accès* : **Utilisateurs**, **Partages** (mène à Compte) · *Système* : **Statistiques**.

- **Vue d'ensemble** : quatre totaux (Releases, Pistes, Stocké, Artistes), puis des blocs titrés par groupe. Chaque
  bloc est une carte : titre, pastille d'état éventuelle, lignes libellé / valeur, boutons.
  - Bibliothèque : **Scan** (état, dernier scan, pistes restant à lire, scan quotidien ; « Gérer le scan »),
    **Contrôle qualité** (Doublons possibles, Sans NFO, Sans année, Sans artiste ; « Tout voir »), **Corrections**
    (nombre par champ ; « Gérer »).
  - Classement : **Règles** (nombre de catégories, artistes, groupes, genres ; « Relancer le classement », « Voir
    les règles »).
  - Accès : **Utilisateurs** (nombre ; « Gérer les utilisateurs »), **Liens de partage** (actifs, ouvertures).
  - Système : **Version** (installée, « À jour » ou « Mise à jour disponible », taille de la base et des vignettes).
- **Scan** : bouton **Lancer le scan** (désactivé pendant un scan), État, Releases trouvées, Pistes restant à lire,
  Début, Fin, Avertissement éventuel ; puis **Scan quotidien** : liste « Jamais », 00:00 à 23:00, et « Heure du
  serveur : 21:40 ».
- **Corrections** : tableau Release, Artiste, Catégorie, Genre, bouton **Retour à l'automatique**. Vide : « Aucune
  correction manuelle. »
- **Règles** : quatre cartes (Catégories, Artistes, Groupes, Genres) avec leur nombre et la règle en une phrase,
  puis **Relancer le classement** ; puis **Artistes rattachés** : tableau Artiste, Rattaché à, bouton **Détacher**.
  Vide : « Aucun artiste rattaché à la main. »
- **Utilisateurs** : tableau Identifiant, Rôle (liste déroulante), Actions (Réinitialiser le mot de passe,
  Supprimer avec confirmation), message par ligne ; puis **Créer un utilisateur**. Le dernier administrateur ne
  peut être ni rétrogradé ni supprimé.

Les deux écrans suivants gardent la même navigation à gauche. Dans le contrôle qualité, chaque ligne porte une
**case à cocher** devant le nom, et un bouton vert **Corriger la sélection (n)** au-dessus de la liste ouvre la boîte
de correction pour toutes les releases cochées (« Corriger 12 releases », champs vides au départ).

- **Statistiques** : une ligne de totaux (« 46 012 releases · 512 300 pistes · 3,2 To · 1 420 jours de musique »),
  puis six tableaux à barres horizontales (libellé, barre, nombre) : **Ajouts par mois**, **Par année**, **Par genre**,
  **Par source**, **Par catégorie**, **Pistes par débit**.
- **Contrôle qualité** : une rangée d'onglets, chacun avec son nombre — **Sans NFO**, **Sans tags**, **Pistes
  illisibles**, **Débit inférieur à 192 kbit/s**, **Sans année**, **Sans pochette**, **Sans piste**, **Sans artiste**, **Doublons possibles** — puis la liste de
  releases concernées. Vide : « Aucune release concernée. »

### 4.13 Page de partage (publique, sans compte)
Page autonome, sans barre du haut ni navigation ni lecteur de l'application : nom de la release ou de la playlist,
**lecteur audio natif du navigateur**, liste des pistes (un clic lit la piste), mention « Partagé avec Mp3 Scene. Ce
lien expire au bout de 7 jours. ». Lien expiré ou révoqué : « Lien de partage invalide ou expiré. »

## 5. Le lecteur

Présent en bas de tous les écrans. C'est l'élément le plus utilisé.

**Contenu**
- **Titre** de la piste (sur deux lignes au besoin) et **nom de la release** (lien vers sa fiche).
- **Commandes** : aléatoire, précédent, **lecture/pause** (bouton principal), suivant, répétition
  (désactivée, toute la file, une piste).
- **Progression** : temps écoulé, **forme d'onde** de la piste servant de barre déplaçable (partie écoutée
  colorée), durée totale. Tant que la forme d'onde n'est pas calculée, un curseur simple la remplace.
- **Outils**, dans cet ordre : volume, **réglages audio (≋)**, file d'attente, bouton Chromecast (quand un appareil
  est disponible).
- **Volume** : curseur **vertical** dans une bulle qui s'ouvre au survol ou au focus du bouton haut-parleur ;
  clic sur le bouton : couper ou rétablir le son. Absent sur téléphone (volume matériel).
- **Messages** brefs dans le lecteur : « Lecture impossible, piste suivante. », « Connexion perdue, nouvelle
  tentative… », « Diffusion sur Salon », « Ajouté à la file : 12 pistes. », « Radio lancée. », « Minuterie : lecture
  arrêtée. », « Lecture bloquée par le navigateur : appuyez sur lecture. »

**File d'attente** (panneau)
- En tête : nombre de pistes, sélecteur **Minuterie** (15 min, 30 min, 60 min, Fin de la piste), bouton
  **Enregistrer** (ouvre la boîte « Ajouter à une playlist » pour toute la file), bouton **Vider la file**, fermeture ×.
- Liste numérotée des pistes, piste en cours marquée ; par ligne : **▲ ▼** (monter, descendre) et **×** (retirer).
  Clic sur une ligne : lecture de cette piste.

**Réglages audio** (boîte de dialogue ouverte par ≋)
- Trois curseurs **Graves**, **Médiums**, **Aigus** (−12 à +12 dB).
- Case **Niveler le volume entre les pistes**.
- Liste **Fondu enchaîné** : Aucun, 2 s, 4 s, 6 s, 8 s, 12 s (grisée sur iPhone).
- Deux textes d'aide (enchaînement sans blanc ; précaution iPhone), boutons **Réinitialiser** et **Fermer**.

**Comportements sans interface propre** (rien à dessiner, mais à ne pas contredire)
- Les pistes s'enchaînent sans blanc ; dix minutes de musique sont chargées d'avance pour passer les coupures de réseau.
- La file, la piste et la position sont reprises sur un autre appareil du même compte, en pause.
- Écran verrouillé et casque : titre, release, pochette et commandes du système (lecture, pause, précédent, suivant).
- Chromecast : le lecteur pilote l'appareil ; l'écran du téléviseur affiche pochette et titre.

**Bureau** : une barre en trois colonnes — informations à gauche, commandes et progression au centre,
outils à droite. Hauteur d'environ 76 px. À gauche, une vignette de 48 px : la pochette, ou la pochette par défaut (disque vinyle sombre à étiquette verte,
« No embedded artwork ») quand la release n'a pas d'image, sur bureau comme sur téléphone. À
droite, sur les écrans d'au moins 1000 px : le débit dans un cadre (« 320 kbps »), le bouton de volume suivi de son
curseur horizontal ; sur le bouton de la file, une pastille verte avec le nombre de pistes.

**Téléphone**, trois états :
1. **Réduit**, au-dessus des onglets : fine ligne de progression, titre, lecture/pause, suivant.
2. **Plein écran**, au toucher du titre, de haut en bas : un bandeau (bouton rond pour réduire, « En cours de
   lecture », Cast, bouton rond vers la fiche de la release) ; la pochette (280 px au plus, coins arrondis) ; le
   titre centré sur une ligne ; le nom de la release en pastille ; la ligne source · débit · groupe
   (« WEB · 320 KBPS · GROUP: AOV ») ; la forme d'onde avec le temps écoulé en vert à gauche et la durée à droite ;
   les commandes larges (bouton lecture de 72 px) ; un bloc d'outils (**DSP/EQ**, **FAV** pour la piste en cours,
   file d'attente en pastille avec le nombre de pistes) ; la mention « Balayez pour changer de piste ». Un balayage
   vers la gauche passe à la piste suivante, vers la droite à la précédente.
3. **File d'attente** en plein écran.

## 6. Bureau et téléphone

| | Bureau (≥ 700 px) | Téléphone (< 700 px) |
|---|---|---|
| Navigation | Dans la barre du haut | **Onglets fixes en bas**, à portée de pouce |
| Liste | Tableau à colonnes libellées, largeur maximale 1400 px | Nom, puis une ligne de détails ; actions à droite |
| Filtres | Trois listes de même largeur, centrées | Trois listes sur une ligne, pleine largeur |
| Lecteur | Barre en trois colonnes | Réduit, puis plein écran |
| Pointage | Souris, survol, clavier | Doigt : cibles de **44 px** au moins |

Sur téléphone, tenir compte des zones sûres (encoche, barre d'accueil) et de l'empilement en bas d'écran :
lecteur réduit **au-dessus** des onglets.

## 7. Contraintes à respecter

**Accessibilité**
- Contraste suffisant en thème clair **et** sombre (les deux existent, selon le réglage du système).
- Tout est utilisable au clavier, avec un focus visible. Raccourcis : Espace (lecture/pause), ← → (± 5 s),
  N (suivant), P (précédent), M (couper le son), / (aller à la recherche), Échap (ferme la file, puis le lecteur
  plein écran).
- Champs de saisie en 16 px au moins sur téléphone (sinon iOS zoome).
- L'état ne repose jamais sur la couleur seule (favori plein ou vide, onglet actif en gras).

**Contenu**
- Noms de release longs (jusqu'à 100 caractères et plus), sans espaces : prévoir le retour à la ligne.
- Champs souvent vides : genre, artiste, durée (tant que les tags ne sont pas lus).
- Une seule image : la **pochette**, sur la fiche et dans le lecteur, souvent absente (prévoir l'affichage sans).
  Une **vignette** de 40 px ouvre chaque ligne des listes ; sans pochette, l'emplacement reste vide.
- Listes très longues : la lisibilité d'une ligne et la vitesse de balayage priment.

**Technique**
- Interface en HTML, CSS et JavaScript sans framework ni étape de build : préférer des composants natifs
  (listes déroulantes, curseurs, tableaux) et des icônes en texte ou en SVG simple.
- Pas de police à télécharger obligatoire : polices système aujourd'hui.

## 8. Habillage actuel (point de départ)

Repris des maquettes Stitch de novembre 2026, décliné en clair et en sombre (selon le réglage du système, ou le
thème choisi dans Compte).

| Élément | Clair | Sombre |
|---|---|---|
| Fond | `#f4f4f0` | `#0c0c0d` |
| Panneaux (barre du haut, lecteur, en-têtes, cartes) | `#ffffff` | `#141415` |
| Survol, puces | `#eaeae4` | `#1c1c1e` |
| Traits | `#d9d9d1` | `#262624` |
| Texte | `#1a1a1a` | `#e8e8e4` |
| Texte secondaire | `#62625c` | `#8e8e88` |
| Accent (bouton principal, onglet actif, progression) | `#22c55e` | `#22c55e` |
| Accent en texte | `#0b7a34` | `#4be277` |
| Information (débit) | `#0369a1` | `#7bd0ff` |
| Erreur | `#b3261e` | `#ffb4ab` |

- **Typographie** : Inter pour l'interface, JetBrains Mono pour les noms de release, les valeurs et les libellés
  (embarquées dans l'application, polices du système en repli). Libellés de colonnes, d'onglets et de sections en
  capitales à chasse fixe de 11 px.
- **Style** : dense et technique ; panneaux délimités par des filets fins, angles de 4 à 8 px, aucune ombre hors
  bulles et panneaux ; genre en puce, débit en bleu, pastille « nouveau » verte **avant** le nom ; entrée de
  navigation active en vert plein (bureau) ; sur téléphone, chaque release est une carte.
- **Icônes** : traits simples, devant les libellés des onglets du bas (téléphone) et des actions de la fiche.

## 9. Maquettes attendues

Pour chaque écran, en **bureau (1440 px)** et **téléphone (375 px)**, thèmes **clair et sombre** :

1. Connexion
2. Derniers, avec filtres, bouton Mix, pastilles « nouveau » et lecteur actif
3. Recherche : onglet Releases sans résultat, onglet Pistes avec résultats
4. Catégories, à deux niveaux de profondeur
5. Explorer : onglet Groupes, puis page d'un groupe
6. Fiche d'une release multi-disques, avec releases similaires et NFO
7. Favoris : les six onglets (Releases, Pistes, Playlists, Hors ligne, Historique, Statistiques)
8. Contenu d'une playlist
9. Boîtes de dialogue : Plus d'actions, Réglages audio
10. Compte d'un utilisateur, avec liens de partage
11. Compte d'un administrateur, scan en cours, bandeau de nouvelle version affiché
12. Bibliothèque : Tableau de bord, Contrôle qualité
13. Mode hors ligne
14. Page de partage publique
15. Lecteur : barre bureau avec bulle de volume ouverte et file ouverte ; sur téléphone, réduit, plein écran et file

États à prévoir : chargement, liste vide, erreur avec « Réessayer », bouton désactivé, favori actif, piste en cours,
téléchargement hors ligne en cours.

## 10. Ce que l'application ne fait pas

À ne pas faire apparaître dans les maquettes :

- Pas d'inscription, de mot de passe oublié, de photo de profil ni de profil public ; aucune fonction sociale
  (abonnements, commentaires, partage entre comptes). Le seul partage est le lien public de 7 jours.
- Pas de notes ni d'étoiles, pas d'étiquettes personnelles, pas de bouton « Suivre », pas de notifications.
- Pas de recommandations hors « Releases similaires » et « Radio » ; pas de page d'accueil éditoriale, de
  carrousels, de « pour vous », de classements globaux.
- Pas de pages d'album ou d'artiste illustrées : pas de photo d'artiste, pas de biographie, pas de paroles.
  La seule image est la pochette de la release.
- Pas d'édition des tags, des noms ni des fichiers ; pas d'envoi de musique ; pas de suppression de release.
- Pas de playlists intelligentes ni partagées entre comptes, pas d'import ou d'export de playlists.
- Pas de détection de doublons, pas de scrobbling (Last.fm…).
- Pas de choix de couleur dans l'interface (seulement le thème : système, clair ou sombre), pas de choix de qualité
  audio, pas de paroles ni de visualiseur autre que la forme d'onde.
- Pas d'achat, d'abonnement ni de publicité.
