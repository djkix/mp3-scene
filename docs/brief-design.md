# Mp3 Scene — descriptif pour maquette

Document destiné à un designer. Il décrit le produit tel qu'il fonctionne aujourd'hui (version 1.1.0) :
à qui il sert, ses écrans, les données affichées, les états et les contraintes à respecter.
L'habillage visuel actuel est décrit à la fin ; il peut être remis en cause, les contraintes ne le peuvent pas.

## 1. Le produit en bref

Mp3 Scene est une application web privée, auto-hébergée, pour **parcourir et écouter une collection de
releases MP3 « scene »** stockée sur un NAS. Une release est un dossier nommé selon une convention stricte,
par exemple `VA-Toolroom_Ibiza_2026-(TOOL142001Z)-WEB-2026-AOV`, qui contient de 1 à plus de 50 pistes.

- **Taille réelle** : environ 46 000 releases, de 10 Mo à 1 Go chacune.
- **Usage** : retrouver une release, la lancer, enchaîner, écouter longtemps (mixes d'une heure et plus).
- **Appareils** : ordinateur (navigateur) et téléphone (application installée, PWA). Les deux comptent autant.
- **Langue** : français uniquement.
- **Ce que l'appli ne fait pas** : pas de playlists, pas d'édition, pas d'écoute hors ligne.

## 2. Utilisateurs

| Profil | Ce qu'il fait | Particularités |
|---|---|---|
| **Utilisateur** | Parcourt, cherche, écoute, met en favori, télécharge | Quelques proches du propriétaire |
| **Administrateur** | Tout cela, plus : comptes, scan de la bibliothèque, mise à jour | Voit les sections d'administration dans Compte et le bandeau de nouvelle version |

Ce sont des connaisseurs : le **nom brut de la release est l'information principale**, il doit rester lisible
en entier, en police à chasse fixe, sans être tronqué.

## 3. Structure générale

Trois zones permanentes, une fois connecté :

1. **Barre du haut** : nom du site (lien vers l'accueil), champ de recherche, navigation.
2. **Contenu** : l'écran courant.
3. **Lecteur** : fixé en bas, visible dès qu'une piste a été lancée, sur tous les écrans.

Navigation, cinq entrées : **Derniers** (accueil), **Dossiers**, **Explorer**, **Favoris**, **Compte**. L'entrée active est marquée.

Un **bandeau** peut apparaître sous la barre du haut, pour les administrateurs :
« Nouvelle version 1.2.0 disponible (installée : 1.1.0). Voir les nouveautés ».

## 4. Écrans

### 4.1 Connexion
- Titre « Mp3 Scene », champs **Identifiant** et **Mot de passe**, bouton **Se connecter**.
- Erreurs : identifiants incorrects ; compte bloqué 15 minutes après 5 échecs.
- Pas d'inscription, pas de mot de passe oublié (les comptes sont créés par un administrateur).

### 4.2 Derniers (accueil) et Recherche
Liste des releases, la plus récente en premier. La recherche (champ de la barre du haut, résultats au fil de la
frappe) affiche la même liste, filtrée.

- **Filtres**, centrés au-dessus de la liste : **Localisations**, **Genres**, **Années** (listes déroulantes ;
  jusqu'à plusieurs dizaines de genres).
- **Colonnes**, dans cet ordre, avec libellé en tête, séparées par de l'espace sans trait vertical :

| Colonne | Exemple | Remarques |
|---|---|---|
| Vignette | pochette 40 px | Sans libellé ; vide s'il n'y a pas de pochette |
| Nom | `VA-Toolroom_Ibiza_2026-(TOOL142001Z)-WEB-2026-AOV` | Chasse fixe, peut passer sur deux lignes, jamais tronqué |
| Genre | House | Centré ; peut être vide tant que les tags ne sont pas lus |
| Date | 26/05/2026 | Centré ; date d'ajout |
| Pistes | 52 | Centré |
| Débit | 320 kbit/s | Centré ; moyenne des pistes, vide tant que les tags ne sont pas lus |
| Poids | 934 Mo | Aligné à droite |
| Localisation | 02.Various Artists - Compilations | Dossier de premier niveau ; tronqué avec info-bulle |
| Actions | + ♡ › | Ajouter à la file, favori (plein quand actif), ouvrir la fiche |

- **Clic sur une ligne** : lance la lecture de la release. Les trois actions sont des cibles distinctes.
- Défilement infini (50 par page). Messages : « Chargement… », « Fin de la liste », « Aucun résultat »,
  erreur avec bouton « Réessayer ».

### 4.2 bis Explorer
- **Onglets** Groupes, Artistes, Genres. Chaque onglet : tableau Nom, Releases, Poids ; en-têtes cliquables pour trier ; champ « Filtrer la liste… », sélecteurs Genre et Année ; total en bas. Au plus 1000 lignes affichées.
- **Page d'un groupe ou d'un artiste** : titre « Groupes › NOM » suivi du nombre de releases et du poids, puis la liste de releases habituelle avec ses filtres. Un genre ouvre la liste Derniers filtrée.
- **Recherche** : onglets Releases et Pistes ; l'onglet Pistes liste les pistes dont le titre ou l'artiste contient les mots cherchés.
- **Hors ligne** : bouton « Garder hors ligne » / « Retirer du hors-ligne » sur la fiche (progression « Téléchargement 3/12… ») ; sans serveur, l'application n'affiche que le bandeau « Serveur injoignable : mode hors ligne. », la liste des releases gardées et le lecteur.
- **Favoris** : onglets Releases, Pistes, Playlists, Hors ligne, Historique, Statistiques. Playlists : tableau (nom, pistes, durée, lire, renommer, supprimer) et contenu d'une playlist. Statistiques : sélecteur de période, total, quatre classements.
- **Actions d'une piste** : bouton ⋯ sur chaque piste, boîte de dialogue avec « Lire ensuite », « Ajouter à la file », puis les playlists et un champ « Nouvelle playlist ».
- **File d'attente** : sélecteur de minuterie, « Enregistrer », « Vider la file » ; chaque ligne a ▲ ▼ ×.
- **Listes de releases** : bouton Mix à côté des filtres ; pastille « nouveau » après le nom ; ligne « N nouvelles releases depuis votre dernière visite » en tête de Derniers.
- **Réglages audio** : bouton ≋ du lecteur, boîte de dialogue avec trois curseurs (graves, médiums, aigus, −12 à +12 dB), une case « Niveler le volume entre les pistes », un sélecteur « Fondu enchaîné », « Réinitialiser ».
- **Compte** : section « Liens de partage » (nom, échéance, ouvertures, Copier, Révoquer) ; pour un administrateur, section « Bibliothèque » menant au tableau de bord (tableaux à barres) et au contrôle qualité (onglets par contrôle, avec leur nombre, puis liste de releases).
- **Page de partage** (/s/…, sans compte) : nom, lecteur natif, liste des pistes, mention d'expiration.

### 4.3 Dossiers
- **Fil d'Ariane** : Dossiers › 02.Various Artists - Compilations › -=Kontor=-
- Liste des **sous-dossiers**, puis la **liste des releases** du dossier (mêmes colonnes qu'à l'accueil).
- Messages : « Dossier vide. », « Dossier introuvable. »

### 4.4 Fiche d'une release
- **Nom** de la release en titre.
- **Pochette** à gauche des informations (au-dessus sur téléphone), quand la release en a une ; un clic l'ouvre en grand.
- **Informations** (les champs absents ne s'affichent pas) : Artiste, Titre, Source (WEB, CD, VINYL, SAT…),
  Année, Groupe, Localisation, Genre, Taille, Durée.
- **Actions** : **Lire** (principale), **Ajouter à la file**, **Favori**, **Télécharger (zip)**.
- **Tableau des pistes** : N°, Artiste - Titre (ou nom de fichier à défaut), Durée, Débit, Genre (colonnes centrées ; Débit en kbit/s,
  masqué sur téléphone), favori de la piste, téléchargement de la piste. Séparateurs « CD 1 », « CD 2 » pour
  les releases multi-disques. Clic sur une piste : lecture à partir de cette piste.
- **NFO** : bloc de texte en chasse fixe, art ASCII, centré ; sur téléphone la police est réduite pour que
  toute la largeur soit visible sans défilement horizontal.

### 4.5 Favoris
- Deux onglets : **Releases** (même liste qu'à l'accueil) et **Pistes** (durée, artiste, titre, release
  d'origine en lien, retrait du favori).
- Messages : « Aucune release favorite », « Aucune piste favorite ».

### 4.6 Compte
- Identifiant et rôle affichés.
- **Changer le mot de passe** : mot de passe actuel, nouveau, bouton, message de succès ou d'erreur.
- **Session** : bouton **Se déconnecter**.

### 4.7 Administration (dans la page Compte, administrateurs seulement, avant « Session »)
- **Utilisateurs** : tableau Identifiant, Rôle (liste déroulante), Actions (Réinitialiser le mot de passe,
  Supprimer avec confirmation). Message par ligne. Le dernier administrateur ne peut être ni rétrogradé ni supprimé.
- **Créer un utilisateur** : identifiant, mot de passe, rôle, bouton **Créer**.
- **Scan de la bibliothèque** : bouton **Lancer le scan** (désactivé pendant un scan, qui peut durer des heures),
  puis État (Au repos, Analyse des dossiers…, Lecture des tags…, Erreur), Releases trouvées, Pistes restant à
  lire, Début, Fin, Avertissement éventuel.
- **Version** : « Version installée : 1.1.0 — à jour. » ou annonce de la nouvelle version.

## 5. Le lecteur

Présent en bas de tous les écrans. C'est l'élément le plus utilisé.

**Contenu**
- **Titre** de la piste (sur deux lignes au besoin) et **nom de la release** (lien vers sa fiche).
- **Commandes** : aléatoire, précédent, **lecture/pause** (bouton principal), suivant, répétition
  (désactivée, toute la file, une piste).
- **Progression** : temps écoulé, **forme d'onde** de la piste servant de barre déplaçable (partie écoutée
  colorée), durée totale. Tant que la forme d'onde n'est pas calculée, un curseur simple la remplace.
- **Outils** : volume, file d'attente, bouton Chromecast (quand un appareil est disponible).
- **Volume** : curseur **vertical** dans une bulle qui s'ouvre au survol ou au focus du bouton haut-parleur ;
  clic sur le bouton : couper ou rétablir le son. Absent sur téléphone (volume matériel).
- **File d'attente** : panneau listant les pistes à venir, piste en cours marquée, retrait d'une piste,
  vidage de la file.
- **Messages** : erreur de lecture, « Diffusion sur <appareil> » pendant un cast.

**Bureau** : une barre en trois colonnes — informations à gauche, commandes et progression au centre,
outils à droite. Hauteur d'environ 76 px.

**Téléphone**, trois états :
1. **Réduit**, au-dessus des onglets : fine ligne de progression, titre, lecture/pause, suivant.
2. **Plein écran**, au toucher du titre : bouton pour réduire, titre et release en grand, progression,
   commandes larges (bouton lecture de 72 px), outils. Un balayage vers la gauche passe à la piste suivante,
   vers la droite à la précédente.
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
  Échap (ferme la file, puis le lecteur plein écran).
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

| Élément | Clair | Sombre |
|---|---|---|
| Fond | `#fafaf8` | `#0c0c0c` |
| Texte | `#1a1a1a` | `#e8e8e4` |
| Texte secondaire | `#6b6b66` | `#8e8e88` |
| Traits | `#deded8` | `#242422` |
| Survol | `#efefe9` | `#181817` |
| Accent (bouton principal, progression) | `#1db954` | `#1db954` |
| Accent en texte | `#0e7a35` | `#1db954` |
| Erreur | `#b3261e` | `#f2766e` |

- **Typographie** : police système sans empattement, 14 px ; noms de release en chasse fixe, 13 px ;
  informations secondaires en 12 px.
- **Style** : sobre et dense, traits fins horizontaux entre les lignes, angles peu arrondis (3 px),
  aucune ombre hors bulles et panneaux.

## 9. Maquettes attendues

Pour chaque écran, en **bureau (1440 px)** et **téléphone (375 px)**, thèmes **clair et sombre** :

1. Connexion
2. Derniers, avec filtres et lecteur actif
3. Recherche sans résultat
4. Dossiers, à deux niveaux de profondeur
5. Fiche d'une release multi-disques avec NFO
6. Favoris, onglets Releases et Pistes
7. Compte
8. Compte d'un administrateur, scan en cours, bandeau de nouvelle version affiché
9. Lecteur : barre bureau avec bulle de volume ouverte et file ouverte ; sur téléphone, réduit, plein écran et file

États à prévoir : chargement, liste vide, erreur avec « Réessayer », bouton désactivé, favori actif, piste en cours.
