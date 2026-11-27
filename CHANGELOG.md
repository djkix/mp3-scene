# Journal des modifications

Toutes les modifications notables de Mp3 Scene sont consignées ici, la plus récente en premier.
Le projet suit le [versionnage sémantique](https://semver.org/lang/fr/). Ce journal est repris dans le
[README](README.md#historique-des-versions).

## [1.85.18](https://github.com/djkix/mp3-scene/compare/v1.85.17...v1.85.18) (2026-11-27)

### Résumé

**« Artiste-Titre » aussi devant une date ou un sous-titre.**

- Release P2P nommée « Artiste_-_Titre » : le séparateur devient « - » même quand une date ou un sous-titre suit
  (« Carl_Cox_-_Inox_…_(11-05-2013)-P2P » -> « Carl_Cox-Inox_…_(11-05-2013)-P2P »). 869 releases renommées au prochain
  scan ; « VA-… », qui a déjà son séparateur, garde son nom.

## [1.85.17](https://github.com/djkix/mp3-scene/compare/v1.85.16...v1.85.17) (2026-11-27)

### Résumé

**Chapitre en cours surligné.**

- Fiche d'un long mix à chapitres (fichier .cue) : le chapitre en cours de lecture est surligné en vert dans la liste
  des chapitres, et le surlignage suit l'écoute, un saut de chapitre ou un déplacement dans la piste.

## [1.85.16](https://github.com/djkix/mp3-scene/compare/v1.85.15...v1.85.16) (2026-11-27)

### Résumé

**Disques imbriqués et « Bonus » rattachés, genre de l'artiste, « Artiste-Titre-année-P2P » pour toutes les releases.**

- « Dmc Commercial Collection 203/Disk 1/title/… » : un sous-dossier au nom de disque (« Disk 1 », « CD2 ») n'était
  lu qu'à son premier niveau ; vide, son sous-dossier « title » devenait une release à part (« title-P2P »). Ses
  pistes, à toute profondeur, sont désormais celles du disque : 9 DMC (203 à 218) réunies au prochain scan.
- Un sous-dossier « Bonus » (ou « Extras », « Bonus CD »…) d'une release est son disque suivant, et non une release à
  part nommée « Bonus » : « VA-Club Addiction (Bootleg) », les Essential Mix Classic de Daft Punk et de Massive Attack.
  Ces releases sont relues une fois au prochain scan.
- Release sans genre (tags vides, souvent un set) : le genre le plus fréquent de son artiste dans la bibliothèque
  (Axwell -> Progressive House). 576 releases en reçoivent un ; un genre lu dans les tags ou corrigé à la main l'emporte.
- Toute release sans groupe ou sans année dans son nom est nommée comme une release P2P, « Artiste-Titre-année-P2P » :
  « Air_-_Moon_Safari » -> « Air-Moon_Safari-1998-P2P », « Mano Solo - Dehors » -> « Mano_Solo-Dehors-2000-P2P ».
  L'année est celle de la release (tags, NFO) et s'ajoute dès qu'elle est connue ; un nom au groupe de scène
  (« …-2006-TGX ») ne change pas. Remplace la règle des compilations de la 1.85.10 ; environ 3 600 releases renommées.

## [1.85.15](https://github.com/djkix/mp3-scene/compare/v1.85.14...v1.85.15) (2026-11-27)

### Résumé

**Une release au numéro de catalogue n'est pas un live.**

- Un nom avec un numéro de catalogue (« Mark_Knight-Untold_Business-(TOOL104201Z)-WEB-2021-AOV ») est une sortie
  commerciale, même s'il cite un festival (Untold, Mayday, Sensation, Tomorrowland…) ou si son groupe est ASOT : il
  reste un single, ou un album à partir de dix pistes, au lieu de Live & Radio. 20 releases concernées.

## [1.85.14](https://github.com/djkix/mp3-scene/compare/v1.85.13...v1.85.14) (2026-11-27)

### Résumé

**Lecture des tags sans « database is locked », colonne Labels.**

- Lecture des tags : « database is locked » quand la position du lecteur était enregistrée pendant le regroupement
  des artistes (une lecture dans une transaction déjà ouverte, puis une écriture d'une autre connexion, faisait
  échouer l'écriture suivante sans attendre). Chaque transaction prend désormais le verrou d'écriture dès son début,
  en attendant son tour.
- Labels : le nombre de labels d'une famille a sa colonne, avant les releases, comme pour les séries.

## [1.85.13](https://github.com/djkix/mp3-scene/compare/v1.85.12...v1.85.13) (2026-11-27)

### Résumé

**Navidrome : lecteur, page d'un album et favori ; séries triées par nombre de releases ; The Essential Selection.**

- Lecteur, morceau Navidrome : « Artiste - Album » en titre, le titre du morceau en dessous.
- Page d'un album Navidrome : « Artiste - Album » en en-tête (l'artiste mène à sa page), aligné à gauche avec les
  boutons ; un bouton Favori met l'album en favori dans Navidrome ; le bloc « Infos » (commentaire des tags) est retiré.
- Onglet Navidrome : contour vert quand il n'est pas sélectionné, pour le repérer.
- Séries : triées par nombre de releases décroissant par défaut ; le nombre de séries d'une famille a sa colonne,
  avant les releases.
- « The Essential Selection » (Pete Tong) est une émission de radio : ses épisodes ont leur page dans Live & Radio. Les
  sets et épisodes de Live & Radio ne forment plus de séries (« The Essential » mélangeait l'émission et des albums).

## [1.85.12](https://github.com/djkix/mp3-scene/compare/v1.85.11...v1.85.12) (2026-11-27)

### Résumé

**Navidrome : « Artiste - Album » dans les listes de morceaux.**

- Recherche, derniers ajouts, morceaux au hasard ou les plus écoutés, page d'un artiste : chaque morceau s'affiche
  « Artiste - Album » (le titre seul ne distingue pas plusieurs versions d'« I Follow Rivers ») ; le titre reste en
  infobulle, et dans la page d'un album.

## [1.85.11](https://github.com/djkix/mp3-scene/compare/v1.85.10...v1.85.11) (2026-11-27)

### Résumé

**Sets d'un dossier en vrac : sans numéro de piste dans le nom et l'artiste.**

- Un set nommé d'après son fichier perd son numéro de piste : « 01.Michael_Burian_-_Sensation_White_Prague_31-05-2008 »
  devient « Michael_Burian_-_Sensation_White_Prague_31-05-2008 », artiste Michael Burian (et non « 01.Michael
  Burian ») ; idem pour les sets INOX 2009 (« 01-dave_clarke_-_live_at_inox… »).

## [1.85.10](https://github.com/djkix/mp3-scene/compare/v1.85.9...v1.85.10) (2026-11-27)

### Résumé

**P2P à la fin des compilations sans groupe, VA devant les DMC, disques imbriqués.**

- Compilation sans groupe à la fin de son nom : « -P2P » ajouté (« VA-Kontor_Top_of_The_Clubs_Vol_01-2CD-1998-P2P »,
  « Ministry_of_Sound_-_Clubbers_Guide_2010-P2P »). Pas pour un disque nommé d'après sa release (« …_(CD2) »).
- Release d'une série sans nom de release : VA en tête, « VA-DMC_Commercial_Collection_054-P2P ».
- Série de compilations : les pistes des sous-dossiers d'un disque en font partie (« Dmc Commercial Collection
  204/Disk2/title » : disque 2 de la 204). Ces releases sont relues une fois au prochain scan.

## [1.85.9](https://github.com/djkix/mp3-scene/compare/v1.85.8...v1.85.9) (2026-11-27)

### Résumé

**Essential Mix en P2P, une pastille par artiste, « Tout rattacher ».**

- Essential Mix : le nom finit par son groupe, « Carl_Cox-Essential_Mix-1994-10-09-TALiON », sinon par P2P
  (« Laurent_Garnier-Essential_Mix-2000-01-30-P2P »). Seul un nom de scène (« …-1994-TALiON ») donne un groupe :
  « Fergie », « Sasha »… lus à la fin d'un nom de dossier ne sont plus des groupes.
- Crédit à plusieurs (« Axwell, Pete Tong and David Guetta ») : une pastille par artiste sur la fiche, chacune vers
  sa page. Coupé aux virgules, et à « and », « & », « vs », « b2b »… seulement si chaque partie est un artiste de la
  bibliothèque : « Cass and Slide » reste un duo. Sur la page d'un artiste, l'onglet « Avec » trouve aussi les mixes
  où il est cité dans une liste (« Axwell,_Pete_Tong… »).
- Les artistes écrits par le renommage des Essential Mix, des épisodes et des disques prennent la graphie la plus
  répandue (« deadmau5 », « Armin van Buuren » -> « Deadmau5 », « Armin Van Buuren ») : ces rapprochements ne sont
  plus proposés.
- Admin › Règles : un bouton « Tout rattacher » accepte d'un coup les rapprochements suggérés.

## [1.85.8](https://github.com/djkix/mp3-scene/compare/v1.85.7...v1.85.8) (2026-11-27)

### Résumé

**Séries de compilations : une seule release avec ses disques, nommée « Titre-année-P2P ».**

- Dans une série du dossier Compilations (« -=DMC Commercial=- », « -=Ministry Of Sound=- »…), les sous-dossiers
  d'une release qui ont des pistes sont ses disques, quel que soit leur nom : « Dmc Commercial Collection 047 » est
  une release de 3 CD (« Mixes 1 », « Mixes 2 », « Previews »), plus trois releases à part. Le numéro du disque vient
  de son nom quand il y en a un, sinon c'est le premier libre dans l'ordre des noms. Les dossiers de pochettes, sans
  pistes, restent ignorés ; les dossiers de collection (« !Hed Kandi - Collection… ») ne changent pas.
- Une release de série dont le dossier n'a pas un nom de release est nommée « Titre-année-P2P »
  (« DMC_Commercial_Collection_339-2011-P2P ») : année du dossier, sinon des tags. Artiste : VA. Les mots de la série gardent
  sa graphie : « Dmc Commercial Collection 047 » devient « DMC_Commercial_Collection_047-1986-P2P ».
- Au prochain scan, ces releases sont relues une fois ; les anciennes releases par disque disparaissent (leurs
  favoris et écoutes repartent de zéro).

## [1.85.7](https://github.com/djkix/mp3-scene/compare/v1.85.6...v1.85.7) (2026-11-27)

### Résumé

**Séries de compilations : chaque sous-dossier avec des pistes est un disque ; P2P pour les releases sans groupe.**

- Dans une série du dossier Compilations (« -=DMC Commercial=- »), tout sous-dossier d'une release qui a des pistes
  est un de ses disques, quel que soit son nom (« Mixes 1 », « International », « CD.2 », « New Folder ») : il prend
  le nom de la release suivi de son disque (« Dmc_Commercial_Collection_047_(CD3_-_Previews_December_1986) »). Le
  numéro vient du nom quand il y en a un, sinon c'est le premier libre dans l'ordre des noms. Un disque seul prend le
  nom de la release, sauf s'il a déjà un nom de release. Les dossiers de pochettes, sans pistes, restent ignorés.
- Un disque garde son année quand le dossier de la release n'en indique pas.
- Une release sans groupe dans son nom (2 040 aujourd'hui) est rangée dans le groupe P2P.

## [1.85.6](https://github.com/djkix/mp3-scene/compare/v1.85.5...v1.85.6) (2026-11-26)

### Résumé

**Lien 1001Tracklists réparé, biographie à côté de la photo.**

- 1001Tracklists ne lit pas une recherche passée dans son adresse (« At least 2 characters are required ») : le picto
  ouvre une recherche Google limitée à 1001tracklists.com. Mots cherchés : l'artiste, le festival ou l'émission et
  l'année pour un set (« Sub Focus Tomorrowland 2025 »), sinon l'artiste, le titre sans dates ni redites et l'année.
- Page d'un artiste : en bandeau, sa photo et sa biographie côte à côte ; dessous, le tableau des listes et les
  pastilles, plus aérés. La biographie est dans la langue de l'application (l'autre à défaut), sans bouton FR / EN.

## [1.85.5](https://github.com/djkix/mp3-scene/compare/v1.85.4...v1.85.5) (2026-11-26)

### Résumé

**Lecteur plein écran sans débordement, lien 1001Tracklists.**

- Lecteur plein écran sur téléphone : tout tient dans l'écran (la pochette s'ajuste à la hauteur, jusqu'aux petits
  téléphones), la page ne bouge plus.
- Fiche d'une release : picto 1001Tracklists après Beatport, qui cherche la tracklist du mix avec l'artiste, le titre
  et l'année, sans soulignés.

## [1.85.4](https://github.com/djkix/mp3-scene/compare/v1.85.3...v1.85.4) (2026-11-26)

### Résumé

**Navidrome : le plus récent d'abord.**

- Onglet Navidrome : pistes et albums de la recherche, et pistes de la page d'un artiste, du plus récent au plus ancien
  (année des tags), puis par titre.

## [1.85.3](https://github.com/djkix/mp3-scene/compare/v1.85.2...v1.85.3) (2026-11-26)

### Résumé

**Pistes disparues retirées, Defected In The House réuni.**

- Un fichier supprimé dans un sous-dossier de disque (CD1/…) n'est plus gardé par la base : quand la lecture de ses
  tags ou de sa pochette le trouve absent, la release est relue au scan suivant, qui le retire. Au premier scan après
  la mise à jour, les doublons « (1) » supprimés à la main sont vérifiés une fois (fin du message « pochette non
  vérifiée … No such file or directory »).
- Labels : « ITH Ltd. », « In The House/Defected », « ITH/Defected », « Defected/ITH », « Defected (In The House) »,
  « ITH Music Services »… réunis sous « Defected In The House », dans la famille Defected.
- Fiche d'une release : les deux groupes de pictos centrés ; sur ordinateur, plus d'espace autour d'eux et entre eux.

## [1.85.2](https://github.com/djkix/mp3-scene/compare/v1.85.1...v1.85.2) (2026-11-26)

### Résumé

**Un set par release dans les dossiers de sets en vrac, titre des émissions cliquable, épisodes distincts.**

- « Paul Van Dyk - Live At The Gallery Turnmills (1999) » : année 1999, titre sans l'année. Les releases sans année
  la reprennent de leur nom au démarrage.
- Dossiers de Live & Radio aux sets en vrac (« -= Tomorrowland 2013 =- », « Essential Mix Collection 2005 ») : chaque
  fichier est une release à part, nommée d'après lui (« Radio_Soulwax-Essential_Mix-2005-01-02 »), avec l'année du
  dossier ; le dossier n'apparaît plus dans les listes. Le festival ou l'émission vient du dossier. Lecture, NFO (son
  .txt) et zip (son seul fichier) se font depuis le dossier. Au premier scan après la mise à jour, ces dossiers sont
  relus une fois et découpés.
- Un live n'est plus pris pour le volume d'une série (« Live at INOX 2012 »).
- Fiche d'une release : une ligne, deux groupes de pictos ronds de même taille, chacun dans sa pastille : écouter et
  garder, puis autour de la release (Discogs, Beatport, YouTube, dossier, pochette). Le dossier s'ouvre dans une
  fenêtre avec son chemin et « Copier le chemin ».
- Fiche d'un set de festival ou d'un épisode d'émission : son titre (« Essential Mix ») mène à sa page de Live & Radio.
- Autres versions : un live ou une émission d'une autre année ou d'un autre jour n'en est plus une (deux
  « Darren_Emerson-Essential_Mix », 1994 et 1999, sont deux épisodes).

## [1.85.1](https://github.com/djkix/mp3-scene/compare/v1.85.0...v1.85.1) (2026-11-26)

### Résumé

**Discographies rangées par type, disques d'un album nommés d'après lui, labels en cartes.**

- Discographie rangée par type (« Jean Michel Jarre/Albums/(1976) - Oxygene ») : chaque release prend un nom complet
  (« Jean_Michel_Jarre-Oxygene-1976 »), son titre entier (« Oxygene 7-13 » au lieu de « Oxygene 7 ») et la catégorie de
  son dossier : Albums, Compilations, Soundtracks et Tributes en Albums, Concerts en Live & Radio, « Singles, Maxis,
  Promos » en Singles.
- Disques d'un album sans nom de release (« Alcazar - Dancefloor Deluxe/Dancefloor Deluxe Disc 2 »,
  « DJMAX Portable 2 Audio Trinity O.S.T/-Black- ») : « Alcazar_-_Dancefloor_Deluxe_(CD2) »,
  « DJMAX_Portable_2_Audio_Trinity_O.S.T_(Black) ». Un sous-dossier daté (dossier de collection) reste une release à part.
- Pictos : infobulle immédiate au survol de la souris ou au focus clavier, dans le style de l'application, sur tous
  les boutons et liens sans texte (fiche, listes, lecteur), au lieu de l'infobulle lente du navigateur.
- En-tête d'un artiste, d'un label ou d'un groupe : plus d'espace entre Artistes, Genres et Groupes, intitulés à la taille du reste.
- Explorer › Labels : les plus fournis d'abord par défaut.
- Photos d'artistes : sans photo au même nom, la première proposée par Deezer. Une recherche restée sans résultat
  (souvent une panne passagère) est refaite au bout d'une semaine, au lieu d'être retenue pour toujours ; une photo
  retirée par un administrateur ne revient pas. Les photos restées vides sont cherchées de nouveau dès la mise à jour.
- Live & Radio : Electric Zoo, Mix Mission et Amsterdam Dance Event (« ADE » d'une diffusion) sont des festivals, avec
  leur année (« Mix Mission » 2009 et non « Mix Mission 2009 »).
- Live & Radio : « INOX Strasbourg 2010 » rejoint le festival INOX Electronique Festival.
- Single ou album rangé dans le dossier des lives sans rien d'un live (référence de catalogue, remixes, tag SINGLE ou
  plusieurs CD, comme « Toni_Braxton-Make_My_Heart_(Part_1)_(MuthaFunkaz_Remixes)-(CODE47)-WEB-2010-HFT ») : classé
  comme dans le dossier des singles.
- Nom d'une release : toujours une capitale en première lettre à l'écran (« Pete_tong_-_the_essential_selection-… »).
- Page d'une famille de labels : une carte par label, avec son logo, son nom et son nombre de releases (deux colonnes
  sur téléphone), au lieu de petits boutons.

## [1.85.0](https://github.com/djkix/mp3-scene/compare/v1.84.5...v1.85.0) (2026-11-26)

### Résumé

**Biographie des artistes en français et en anglais.**

- Page d'un artiste : sa biographie, en anglais d'après son profil Discogs et en français d'après le résumé de son
  article Wikipédia (retrouvé par le lien Wikipédia de Discogs). La langue de l'interface d'abord, un bouton FR / EN
  pour l'autre ; quatre lignes et « Lire la suite » ; la source en lien. Gardée un mois dans les données de
  l'application. Il faut un jeton `DISCOGS_TOKEN`.
- Lecteur plein écran : un picto devant le genre (étiquette) et devant la catégorie (dossier).
- Sous-dossiers d'une compilation sans nom de release (« SALSOUL_CD1 », « Uncovered_1 », « Als Mixe CD1 »,
  « 25 Avant Nova - 1956 ») : ils prennent le nom de la compilation suivi de leur disque,
  « VA-The_Salsoul_Acapellas-2CD-2005_(CD1) », « VA-Kontor_Top_of_The_Clubs_Vol_41-3CD-2008_(CD1_-_Als_Mixe) ». Des
  disques tous datés sont numérotés dans l'ordre des années (« VA-La_Boite_Noire_Radio_Nova_(1956-1980)-25CD-2010_(CD1_-_1956) »).
  Artiste, titre, année et groupe sont ceux de la compilation.
- Release d'un artiste rangée dans le dossier d'une compilation VA (« Axer-123__321-Promo_Vinyl-2006-TGX » dans
  « VA-Sunshine_Live_House_Edition_Vol._1-3CD-2006-JiM ») : classée comme dans le dossier des singles, en Singles ou
  en Albums (« Matt-RB_2_Rue-2001-FSP », 13 pistes) au lieu de Compilations.

## [1.84.5](https://github.com/djkix/mp3-scene/compare/v1.84.4...v1.84.5) (2026-11-26)

### Résumé

**Forme d'onde lisible, genre et catégorie dans le lecteur, actions de la fiche en pictos.**

- Forme d'onde : volume moyen de chaque instant au lieu de sa crête. Une musique compressée au mastering touchait le
  maximum presque partout et toutes les barres semblaient pleines ; intro, break et montée se voient maintenant. Les
  formes d'onde déjà calculées le sont de nouveau à la prochaine écoute.
- Lecteur plein écran : genre et catégorie de la release, centrés sous les informations, chacun mène à sa page.
- Mix découpé en chapitres : « artiste - titre · heure » au lieu de « heure · artiste - titre ».
- Fiche d'une release : les huit actions (lire, file, playlist, radio, favori, hors ligne, zip, partager) sur une
  seule ligne de pictos ronds, lecture en grand rond vert ; le nom de chaque action en bulle.

## [1.84.4](https://github.com/djkix/mp3-scene/compare/v1.84.3...v1.84.4) (2026-11-26)

### Résumé

**La pochette lance la lecture.**

- Listes de releases : le picto lecture est posé sur la pochette, en bas à droite ; un appui sur la pochette lance
  la release, un appui ailleurs sur la ligne ouvre sa fiche.
- Lecteur réduit sur téléphone : lecture/pause écartée du titre, suivant et cast resserrés ; la barre de
  progression occupe toute la largeur, collée au bord haut du lecteur.
- Nom d'une release sur téléphone : les deux lignes sont remplies (un long morceau sans tiret ne part plus à une
  troisième ligne cachée, en laissant la deuxième presque vide).
- Fiche d'une release : chemin du dossier sur une ligne (entier en bulle), copie au bout ; Discogs, Beatport,
  YouTube (avec leur logo) et, pour un administrateur, ajouter, chercher ou retirer une pochette sur une seule rangée
  de pictos ronds.
- Listes de pistes et cartes de la fiche : largeur de la première colonne de nouveau correcte (une variable CSS
  partageait son nom avec une couleur des graphiques depuis la 1.84.1).

## [1.84.3](https://github.com/djkix/mp3-scene/compare/v1.84.2...v1.84.3) (2026-11-26)

### Résumé

**Lecteur sur téléphone, Live & Radio sans erreur 422.**

- Lecteur réduit : la barre de progression revient au-dessus du titre, un pixel plus fine ; pochette plus grande.
- Lecteur plein écran : le nom de la release défile s'il est trop long ; l'artiste en plus grand (+2 px).
- « Chercher une photo » devient un picto appareil photo (artistes, labels, festivals).
- Live & Radio › Clubs et autres : les dossiers « -= Winter Music Conference 20xx =- » et « -= White Sensation … =- »
  sont rangés dans Festivals ; un dossier orné sans artiste prend son nom (« INOX Strasbourg 2010 ») au lieu d'un nom
  vide, dont la page renvoyait « Erreur 422 ».

## [1.84.2](https://github.com/djkix/mp3-scene/compare/v1.84.1...v1.84.2) (2026-11-26)

### Résumé

**Pochette plus grande sur téléphone.**

- Listes de releases sur téléphone : pochette de 56 px au lieu de 40, marge de gauche réduite, picto lecture plus
  grand et collé à la pochette.

## [1.84.1](https://github.com/djkix/mp3-scene/compare/v1.84.0...v1.84.1) (2026-11-26)

### Résumé

**Lignes de releases plus claires sur téléphone.**

- Le badge « nouveau » est posé sur la pochette, et le picto lecture se place juste à côté, plus grand pour le doigt.
- Sur téléphone, le nom tient sur deux lignes au plus (le nom complet reste sur la fiche). Dessous, dans l'ordre :
  genre, pistes, débit, poids, catégorie, année.

## [1.84.0](https://github.com/djkix/mp3-scene/compare/v1.83.1...v1.84.0) (2026-11-26)

### Résumé

**Ce qui manque d'un label, d'après Discogs.**

- Page d'un label : un bouton « Ce qui manque » liste ses sorties sur Discogs absentes de la bibliothèque, les plus
  récentes d'abord, avec l'année, la référence, le format et un lien vers la fiche Discogs.
- Une sortie est reconnue à son numéro de catalogue (NFO ou nom du dossier), à son artiste et son titre, ou à son
  titre parmi les releases du label ; les éditions d'un même disque (vinyle, CD, fichier) n'en font qu'une.
- Le bouton n'apparaît qu'avec un jeton `DISCOGS_TOKEN`. Les 500 sorties les plus récentes au plus ; la réponse de
  Discogs est gardée un jour.

## [1.83.1](https://github.com/djkix/mp3-scene/compare/v1.83.0...v1.83.1) (2026-11-25)

### Résumé

**Listes plus lisibles sur téléphone, pochette par défaut.**

- Listes de releases : le badge « nouveau » avant le picto lecture ; sur téléphone, badge et picto plus serrés pour
  laisser la place au nom.
- Une release ou une piste sans pochette affiche la même pochette par défaut que le lecteur, au lieu d'une case vide
  (listes, pistes, sets des festivals, onglet Navidrome).

## [1.83.0](https://github.com/djkix/mp3-scene/compare/v1.82.3...v1.83.0) (2026-11-25)

### Résumé

**Année des tags, pochettes des pistes suivantes, picto lecture.**

- Une release dont le nom ne donne pas l'année (album du web…) prend la plus fréquente dans les tags de ses pistes.
  Au premier scan après la mise à jour, les pistes des releases sans année sont relues une fois.
- Pochette : l'image incluse dans les tags est cherchée dans les trois premières pistes, pas seulement la première.
  Les releases marquées sans pochette sont revérifiées au prochain scan.
- Listes de releases : un picto lecture devant le nom lance la release ; un clic sur la ligne ouvre sa fiche.

## [1.82.3](https://github.com/djkix/mp3-scene/compare/v1.82.2...v1.82.3) (2026-11-25)

### Résumé

**Essential Mix nommés de façon cohérente.**

- Tout Essential Mix s'affiche « Artiste-Essential_Mix-date », quel que soit le format du dossier
  (« 2016-03-19_-_Riva_Starr_&_Axwell_-_Essential_Mix », « Essential Mix_2012_01_07_qrip », « 2015 12 05 Essential Mix
  #1141 - … », noms scene « …-SAT-10-09-1994-GROUPE », « … 2021 Week 50 - … »). L'artiste vient du nom, sinon des
  tags de la piste, sinon d'un nom de fichier qui décrit l'épisode ; un lieu ou une précision (« Live at … »,
  « Master Series 05 », « Part 1 ») rejoint le titre. Artiste, titre, année et date de diffusion sont renseignés.
- Les dossiers « Essential Mix Collection AAAA » qui réunissent leurs mixes en vrac les présentent un par un, nommés
  de la même façon, dans la page de l'émission (Live & Radio › Radio).

## [1.82.2](https://github.com/djkix/mp3-scene/compare/v1.82.1...v1.82.2) (2026-11-25)

### Résumé

**Navidrome : lien de la release et infos de l'album.**

- Lecteur : pour une piste de Navidrome, le nom de la release ouvre sa page d'album dans l'onglet Navidrome (au lieu
  de « Release introuvable »).
- Page d'un album Navidrome : le commentaire des tags de chaque piste (souvent la tracklist d'un mix), les notes de
  l'album quand Navidrome en a (texte seul) et le dossier.

## [1.82.1](https://github.com/djkix/mp3-scene/compare/v1.82.0...v1.82.1) (2026-11-25)

### Résumé

**Navidrome en morceaux, dossiers rangés avec Albums ou Singles, émissions numérotées.**

- Onglet Navidrome : derniers ajouts, au hasard, les plus écoutés et page d'un artiste en liste de morceaux
  (pochette, année, durée), « Voir plus » par pages de 60 ; artistes par lettre, alphabet en haut. La recherche ne
  montre en albums que ceux de plusieurs morceaux.
- `MUSIC_EXTRA` : « Nom=/chemin>albums » ou « >singles » range les releases d'un dossier supplémentaire avec les
  albums ou les singles au lieu d'une catégorie à part.
- Live & Radio : un nom numéroté suivi de son invité (« Bonkers_Beats_266-With_Rob_Da_Rhythm-… ») est l'épisode
  d'une émission ; le tag LIVE suivi d'une source (« …-LIVE-WEB-2026-… ») range la release dans Live & Radio.

## [1.82.0](https://github.com/djkix/mp3-scene/compare/v1.81.3...v1.82.0) (2026-11-25)

### Résumé

**Onglet Navidrome, dossiers de musique supplémentaires.**

- Onglet Navidrome dans Explorer (avec `NAVIDROME_URL`, `NAVIDROME_USER`, `NAVIDROME_PASSWORD`) : derniers ajouts,
  albums au hasard ou les plus écoutés, artistes, recherche et page d'un album, lus dans le lecteur de Mp3 Scene
  (file d'attente, déplacement, Chromecast). Le serveur Mp3 Scene relaie tout : le compte Navidrome ne parvient
  jamais au navigateur. MP3, FLAC, M4A et OGG lus tels quels, le reste converti en MP3 par Navidrome. Pas de
  paroles, forme d'onde, favoris ni historique pour ces pistes.
- Dossiers de musique supplémentaires (`MUSIC_EXTRA`, « Nom=/chemin » séparés par « ; ») : chacun apparaît comme
  un dossier racine de la bibliothèque, donc une catégorie, avec scan, lecture, NFO, pochettes et téléchargement.
  Un dossier non monté au moment du scan garde ses releases.

## [1.81.3](https://github.com/djkix/mp3-scene/compare/v1.81.2...v1.81.3) (2026-11-25)

### Résumé

**Lives d'un artiste : ses sets seulement.**

- Sur la page d'un artiste, un festival, une émission ou « Clubs et autres » de la ligne Lives n'ouvre plus que ses
  sets à lui (son set dans un dossier aux sets en vrac compris). Le titre de la page mène à tous les sets du
  festival et revient à l'artiste.

## [1.81.2](https://github.com/djkix/mp3-scene/compare/v1.81.1...v1.81.2) (2026-11-25)

### Résumé

**Favoris filtrables, épisodes de radio datés renommés.**

- Favoris › Releases : mêmes filtres (catégories, genres, années, sources) et même groupement par type que les
  autres listes, du plus récent au plus ancien.
- Épisodes d'une émission connue rangés « date - émission - artiste » (« 2002-06-09_-_Essential_Mix_-_Michel_de_Hey ») :
  nom affiché « Artiste-Émission-date » (« Michel_de_Hey-Essential_Mix-2002-06-09 »), artiste, titre, année et date
  de diffusion renseignés ; un lieu après « @ » rejoint le titre. Sans artiste, rien à sa place. Le dossier sur le
  disque ne change pas.

## [1.81.1](https://github.com/djkix/mp3-scene/compare/v1.81.0...v1.81.1) (2026-11-25)

### Résumé

**Disques nommés réunis à leur album.**

- Un sous-dossier qui commence par CD, Disc ou Disk suivi d'un numéro est un disque de l'album qui le contient, quoi
  qui suive : « CD3 - Mixed by Axwell », « CD1 [Sunshine Disc] », « CD1 Mixed by … », « Disc1-V-Rock »,
  « Cd 2 (DJ Kost Mix) », « CD1-TDG ». Ils formaient chacun une release à part ; au prochain scan, l'album réuni
  les remplace (favoris et écoutes posés sur les disques séparés ne suivent pas).
- Compilations « année - Ministry of Sound / Hed Kandi - titre [nCD] » : nom affiché « série - titre »
  (« Ministry_of_Sound_-_Clubbers_Guide_2010 »), relu sur le dossier ; année, artiste VA, label et série inchangés.

## [1.81.0](https://github.com/djkix/mp3-scene/compare/v1.80.1...v1.81.0) (2026-11-25)

### Résumé

**Lives rangés dans les Singles.**

- Dans le dossier des singles, une release qui dit « Live at… », « DJ Set @… » ou cite un festival ou une émission
  de radio connus passe dans Live & Radio, même sans tag de diffusion (SAT, FM…), et rejoint la page de son
  festival. Un morceau qui porte le nom d'un festival (« Tomorrowland Anthem », remix, edit) reste un single ; une
  release en CD garde sa catégorie.
- Contrôle qualité « Lives dans le dossier Singles » : les releases de Live & Radio dont le dossier est encore parmi
  les singles sur le disque, à déplacer sur le NAS (l'application ne touche jamais aux fichiers).

## [1.80.1](https://github.com/djkix/mp3-scene/compare/v1.80.0...v1.80.1) (2026-11-25)

### Résumé

**Fiche d'un set d'un dossier aux sets en vrac.**

- Live & Radio : le « i » d'un set rangé avec d'autres dans un même dossier (« -=_INOX_Electronique_Festival_2012_=- »)
  ouvre une fiche à son nom, avec ce seul set et un lien vers le dossier entier.
- Son .txt (ou .nfo) est celui qui porte le même nom que son fichier ; s'il n'en a pas, aucun autre ne s'affiche
  à sa place, sauf si le dossier n'en compte qu'un.

## [1.80.0](https://github.com/djkix/mp3-scene/compare/v1.79.0...v1.80.0) (2026-11-25)

### Résumé

**Fichiers .txt des mixes, silences sautés.**

- Une release sans NFO prend son premier fichier .txt à la place : affiché sur la fiche, et lu comme un NFO
  (tracklist et chapitres des longs mixes, titres des pistes sans tags, date, label, recherche dans les NFO). Texte
  en UTF-8 ou Windows-1252. Au premier scan après la mise à jour, les releases sans NFO sont relues une fois
  (pistes, favoris et écoutes conservés).
- Tracklists : « 01. [00:00] Artiste - Titre » et « 00:00 - Artiste - Titre » sont reconnues.
- Dates en français : « Diffusé le 12/03/2010 », « Date de sortie : … », ou « Date : … » seule.
- Sauter les silences (Réglages audio, activé par défaut) : un blanc d'au moins 1,5 s en début ou en fin de piste,
  ou de 8 s au milieu (avant une piste cachée), repéré sur la forme d'onde, est sauté pendant la lecture.

## [1.79.0](https://github.com/djkix/mp3-scene/compare/v1.78.0...v1.79.0) (2026-11-25)

### Résumé

**Mode soirée, volume égalisé, carte des collaborations.**

- Live & Radio : un dossier d'événement qui réunit ses sets en vrac (« -=_INOX_Electronique_Festival_2012_=- »,
  un fichier par set) les affiche un par un, au même niveau que les autres sets de l'année, et les compte chacun.
- Volume égalisé (Réglages audio, activé par défaut) : le volume moyen de chaque piste est mesuré avec sa forme
  d'onde à la première écoute ; les pistes trop fortes sont baissées. Sans effet sur iPhone (iOS ignore ce volume).
- Carte des collaborations : depuis « Souvent avec » sur la page d'un artiste, ses principaux partenaires en cercle,
  reliés entre eux ; un clic recentre sur l'un d'eux.
- Admin › Statistiques : frise des genres, la part des cinq grandes familles de genres par année de sortie.
- Mode soirée (picto TV du lecteur plein écran) : page seule pour une télé ou une tablette, pochette en grand,
  titre, artiste, pistes à suivre et heure ; elle suit ce qui joue sur n'importe quel appareil du compte.
- Recherche vocale : un micro dans la barre de recherche, avec la reconnaissance du navigateur.
- Pages d'artiste, de label, de groupe, de genre et recherche : dans chaque type, du plus récent au plus ancien.

## [1.78.0](https://github.com/djkix/mp3-scene/compare/v1.77.0...v1.78.0) (2026-11-25)

### Résumé

**Rubriques harmonisées.**

- Page d'une série : releases groupées par type (albums, singles, compilations, live) avec leurs couleurs, l'ordre
  des volumes gardé dans chaque groupe, et les artistes les plus présents à côté des genres et des labels.
- Page d'une année : même en-tête que les labels et les genres (chiffres, artistes, genres, labels).
- Labels, groupes, genres, années : le résumé détaille chaque type (nombre et poids).
- Fiche d'une release : Genre, Année et Catégorie mènent à leur page d'Explorer, plus à une liste filtrée ; les
  genres des statistiques aussi.

## [1.77.0](https://github.com/djkix/mp3-scene/compare/v1.76.3...v1.77.0) (2026-11-25)

### Résumé

**NFO à l'ancienne, lecteur aux couleurs de la pochette, stockage dans Admin.**

- NFO affichés avec la police VGA d'origine (IBM VGA 8 × 16, page de code 437, VileR, CC BY-SA 4.0) : l'art ASCII
  des groupes tombe juste, blocs et cadres compris.
- Lecteur plein écran : le fond prend la teinte de la pochette (mêlée au fond du thème), et les rayons du
  visualiseur aussi ; rien ne change avec une pochette terne ou celle par défaut.
- Admin › Vue d'ensemble : carte « Stockage » avec l'espace libre du NAS et des données, et la taille de la
  collection mois après mois (24 derniers mois).
- Lecteur réduit sur téléphone : les pictos paroles et visualiseur n'y apparaissent plus (plein écran seulement).

## [1.76.3](https://github.com/djkix/mp3-scene/compare/v1.76.2...v1.76.3) (2026-11-24)

### Résumé

- Visualiseur en anneau : la pochette ronde au centre, le spectre rayonne tout autour en traits arrondis (basses en
  haut, aigus en bas, symétrique), à la place du VU-mètre.

## [1.76.2](https://github.com/djkix/mp3-scene/compare/v1.76.1...v1.76.2) (2026-11-24)

### Résumé

- Visualiseur en VU-mètre à segments : colonnes de diodes (couleur d'accent, puis jaune, rouge en haut), avec un
  pic qui retombe, à la place des barres pleines.

## [1.76.1](https://github.com/djkix/mp3-scene/compare/v1.76.0...v1.76.1) (2026-11-24)

### Résumé

- Le panneau des paroles ou du visualiseur se referme à chaque changement de page : il ne masque plus le contenu.

## [1.76.0](https://github.com/djkix/mp3-scene/compare/v1.75.1...v1.76.0) (2026-11-24)

### Résumé

**Familles de labels, paroles, visualiseur et lives d'un artiste.**

- Familles de labels : un label qui commence par le nom d'une maison mère (sans « Records », « Productions », « Ltd »,
  pays entre crochets), ou la porte après une barre, la rejoint. L'onglet Labels montre une ligne « Toolroom » ; sa
  page a un bloc par label. Règles manuelles dans Admin › Règles (rattacher, garder à part, défaire, réunir par début).
- Paroles (LRCLIB, par le serveur, gardées en base par morceau) : un picto dans le lecteur ; en plein écran sur
  téléphone, elles remplacent la pochette, sur ordinateur un panneau au-dessus de la barre. Synchronisées quand la
  version minutée a la même durée (à 8 s près), sinon en texte ; un clic sur une ligne y mène.
- Visualiseur : spectre animé au même endroit, Web Audio créé seulement à son ouverture.
- Page d'un artiste : rubrique « Lives » (festivals, émissions, clubs et autres où il joue).
- Lecteur sur ordinateur : la pastille du format n'apparaît qu'à partir de 1 600 px, pour garder les outils sur une ligne.
- Correctif : la politique de sécurité bloquait depuis la 1.71.0 le son silencieux qui autorise le second élément
  audio sur mobile (enchaînement de la piste suivante).

## [1.75.1](https://github.com/djkix/mp3-scene/compare/v1.75.0...v1.75.1) (2026-11-24)

### Résumé

- « Chercher sur le web » cherche le logo d'un festival, d'une émission ou d'un label (« … logo ») ; la photo pour
  un artiste.

## [1.75.0](https://github.com/djkix/mp3-scene/compare/v1.74.1...v1.75.0) (2026-11-24)

### Résumé

**Vos propres photos.**

- La fenêtre « Chercher une photo » (artistes, labels, festivals, émissions) accepte une image à soi : déposée,
  choisie sur l'appareil, collée (⌘V / Ctrl+V) ou glissée depuis une page web (téléchargée par le serveur, mêmes
  garde-fous que les propositions). Réduite à 600 px, gardée dans les données de l'application.
- Bouton « Chercher sur le web » : Google Images s'ouvre dans un nouvel onglet, le nom déjà saisi.
- Live & Radio : un nom écrit en minuscules dans les fichiers s'affiche avec ses majuscules quand une autre
  graphie en a.

## [1.74.1](https://github.com/djkix/mp3-scene/compare/v1.74.0...v1.74.1) (2026-11-24)

### Résumé

- Live & Radio : la rangée Festivals · Radio · Clubs et autres garde le même écart vertical que les rangées
  d'onglets au-dessus (20 px).

## [1.74.0](https://github.com/djkix/mp3-scene/compare/v1.73.0...v1.74.0) (2026-11-24)

### Résumé

**Live & Radio : festivals, radio, clubs et autres, avec photos.**

- Trois onglets sous Live & Radio : Festivals, Radio et Clubs et autres, chacun avec son mur et la même page rangée
  par année.
- Radio : sets réunis par émission (Essential Mix, A State of Trance, Club Life, Group Therapy…) ; une release de
  source radio (SAT, FM, CABLE…) prend son titre sans numéro d'épisode, à partir de deux épisodes.
- Clubs et autres : le reste des lives, par artiste.
- Photos prises d'office : photo de l'artiste ; pour un festival ou une émission, pochette d'un de ses sets, sinon
  pochette d'album Deezer ou iTunes dont le titre commence par son nom (les éditions datées d'abord). Un
  administrateur peut en choisir une autre ou la retirer depuis la page.

## [1.73.0](https://github.com/djkix/mp3-scene/compare/v1.72.3...v1.73.0) (2026-11-24)

### Résumé

**Live & Radio par festival.**

- La catégorie Live & Radio s'ouvre sur un mur des festivals (Tomorrowland, Ultra Music Festival, INOX…) : pochette
  du set le plus récent, nombre de sets, période ; filtre, et « Toutes les releases » pour la liste habituelle.
- Le festival et son année sont lus dans le nom de la release (« Live at », « Festival … ») ; les graphies d'un même
  festival sont réunies (« INOX Electronique » et « INOX Electronic »).
- Page d'un festival : ses sets du plus récent au plus ancien, un intertitre en pastille par année, et une rangée
  d'années qui mène à chacune.
- Mobile : une ligne pleine largeur par festival, années sur une rangée qui défile au doigt, cibles tactiles de
  44 px ; liste de liens lisible au lecteur d'écran, focus placé sur l'année choisie.

## [1.72.3](https://github.com/djkix/mp3-scene/compare/v1.72.2...v1.72.3) (2026-11-23)

### Résumé

**Cast réparé avec une longue file d'écoute.** La file était envoyée au Chromecast par fenêtres de 100 pistes,
soit environ 78 Ko, au-delà de la limite de 64 Ko des messages Cast : le message était abandonné sans erreur,
le récepteur ne lançait rien. Fenêtres de 40 pistes désormais (environ 35 Ko), la suivante étant chargée à la fin.

## [1.72.2](https://github.com/djkix/mp3-scene/compare/v1.72.1...v1.72.2) (2026-11-23)

### Résumé

**Cast : message quand le récepteur ne peut pas lire la piste** (adresse injoignable, certificat refusé, format
non lu) ; jusqu'ici rien ne se passait, sans explication.

## [1.72.1](https://github.com/djkix/mp3-scene/compare/v1.72.0...v1.72.1) (2026-11-23)

### Résumé

**Tests JavaScript de la CI lancés par motif de fichiers** (Node 22 n'accepte pas un dossier) ; l'image 1.72.0
n'avait pas été construite.

## [1.72.0](https://github.com/djkix/mp3-scene/compare/v1.71.0...v1.72.0) (2026-11-23)

### Résumé

**Corrections issues de l'audit de sécurité externe.**

- **Fichiers** : tags, NFO, `.cue` et pochettes ne sont plus lus à travers un lien symbolique ; seuls les fichiers
  ordinaires sous `/music` sont ouverts.
- **Requêtes** : corps plafonné (1 Mio, 8 Mio pour une pochette) ; requêtes d'un autre site refusées sur `/api/` ;
  conversions et formes d'onde répondent 503 quand le serveur est occupé ; ffmpeg limité aux fichiers locaux.
- **Comptes** : proxys de confiance réglables (`TRUSTED_PROXIES`), IPv6 compté par /64, adresse habituelle jamais
  bloquée, changement de mot de passe limité et journalisé, 20 sessions au plus et bouton « Fermer toutes les autres
  sessions », identifiants en double selon la casse refusés, journal complet des actions d'administration.
- **Données** : `.env` exclu des sauvegardes sauf `BACKUP_ENV=1`, base et sauvegardes en 0600 ; photos cherchées
  seulement pour les noms en base ; téléchargement d'images sur l'adresse déjà vérifiée, signatures valables une
  heure ; corrections et pochette suivent un album déplacé ; 100 playlists au plus.
- **Hors ligne** : liens publics `/s/` exclus du cache, cache vidé à la déconnexion.
- **Livraison** : tests et `pip-audit` avant la construction de l'image ; exemple de compose durci.

## [1.71.0](https://github.com/djkix/mp3-scene/compare/v1.70.0...v1.71.0) (2026-11-23)

### Résumé

**Durcissements de sécurité, statistiques des enrichissements.**

- **En-têtes** : politique de contenu (scripts de l'application et du SDK Cast seulement), interdiction d'affichage
  dans le cadre d'un autre site, politique de référent `same-origin`.
- **Connexion** : cinq essais ratés bloquent le couple identifiant + adresse et l'adresse, plus le compte lui-même ;
  l'identifiant seul garde un plafond large (50 par quart d'heure). X-Forwarded-For n'est cru que d'une connexion
  venue du réseau local (le proxy).
- **Images** : une image de plus de 40 mégapixels est refusée au décodage (pochettes, vignettes, photos) ; les
  vignettes JPEG sont décodées directement en petit.
- **Statistiques** : une section « Enrichissements » — pistes avec BPM et tonalité, chapitres, titres à plusieurs
  versions, séries et familles, photos et logos, rattachements, pistes par tempo, titres et séries les plus présents.

## [1.70.0](https://github.com/djkix/mp3-scene/compare/v1.69.1...v1.70.0) (2026-11-23)

### Résumé

**Page d'un titre : pistes groupées par artiste, tri au clic, filtres.**

- Les pistes d'un titre sont rangées par artiste, les graphies d'un même crédit réunies (« Axwell & Ingrosso »,
  « Axwell /\\ Ingrosso », « Axwell and Ingrosso »), avec un intertitre à chaque artiste.
- Les en-têtes de colonnes (artiste, genre, durée, débit, release) trient au clic, ici et dans l'onglet Pistes de la
  recherche.
- La page d'un titre a les mêmes filtres que la liste des titres (genres, années, catégories).
- Les guillemets autour d'un titre (« 'Strong in Love' ») sont ignorés ; le bouton de lecture aléatoire est retiré.

## [1.69.1](https://github.com/djkix/mp3-scene/compare/v1.69.0...v1.69.1) (2026-11-23)

### Résumé

**Onglet Titres plus rapide, sans titre vide.**

- La liste des titres se calcule trois fois plus vite (le titre nettoyé n'est plus recalculé à chaque usage), et un
  titre fait seulement de signes n'apparaît plus vide.

## [1.69.0](https://github.com/djkix/mp3-scene/compare/v1.68.0...v1.69.0) (2026-11-23)

### Résumé

**Lecture aléatoire d'une page, onglet Années, titres mieux réunis, titres des pistes lus dans le NFO.**

- **Lecture aléatoire** : un bouton sur la page d'un artiste, d'un label, d'un groupe, d'un genre, d'une année, d'une
  série ou d'un titre lance jusqu'à 100 de ses pistes au hasard.
- **Années** : nouvel onglet d'Explorer, une ligne par année (la plus récente d'abord), filtres genre et catégorie ;
  une année ouvre ses releases, groupées par catégorie.
- **Titres** : les versions notées après un tiret (« Show Me Love - Club Mix ») rejoignent leur titre, les signes en
  tête (« _ », « .... ») sont ignorés, et un titre se fusionne à un autre à la main (Administration › Règles).
  « Détail des pistes » montre chaque piste au lieu des regroupements.
- **Pistes sans tags** : elles prennent l'artiste et le titre de la tracklist du NFO quand celle-ci compte exactement
  autant de morceaux (lu au scan, et au premier démarrage de cette version).

## [1.68.0](https://github.com/djkix/mp3-scene/compare/v1.67.0...v1.68.0) (2026-11-23)

### Résumé

**Onglet Titres dans Explorer.**

- Entre Artistes et Genres, la liste des morceaux de la bibliothèque, toutes versions réunies (« Show Me Love »,
  « Show Me Love (Club Mix) »…), avec leur nombre de pistes et leur poids ; mêmes lettres et même tri que la liste des
  artistes, et un filtre Catégories en plus des genres et des années. Seuls les titres présents au moins deux fois
  sont listés.
- Un titre ouvre la liste de toutes ses pistes, quelles qu'en soient la version et la release.

## [1.67.0](https://github.com/djkix/mp3-scene/compare/v1.66.5...v1.67.0) (2026-11-23)

### Résumé

**Écran allumé dans l'application installée, albums d'abord sur toutes les pages, capitales des artistes.**

- **Écran** : installée sur l'écran d'accueil (Android, iOS 16.4 et plus), l'application empêche la mise en veille
  tant qu'elle est affichée ; interrupteur « Garder l'écran allumé » dans les réglages audio.
- **Listes** : les pages d'un label, d'un groupe, d'un genre et la recherche s'ouvrent comme celle d'un artiste —
  albums, singles, compilations, live — avec intertitres et liseré de couleur.
- **Artistes** : un artiste de piste écrit tout en minuscules prend des capitales (« soul vision » -> « Soul Vision »),
  comme les artistes associés de la page d'un artiste.

## [1.66.5](https://github.com/djkix/mp3-scene/compare/v1.66.4...v1.66.5) (2026-11-23)

### Résumé

**Artistes sans souci de casse, titres coupés par un mot de source.**

- La page d'un artiste ignore la casse : ouverte en capitales (« BOB SINCLAR »), elle se range sous la graphie en base.
- Une graphie tout en capitales cède à la graphie mixte, pour les artistes des releases comme pour ceux des pistes.
- Un mot de source au milieu d'un long bout de titre (« …Party_at_Contact_Fm ») compte pour la catégorie sans couper
  le titre : environ 1 200 titres sont mieux lus, relus au démarrage.

## [1.66.4](https://github.com/djkix/mp3-scene/compare/v1.66.3...v1.66.4) (2026-11-23)

### Résumé

**Logo des labels, intertitres au style des années, RADIO dans Live & Radio, dossiers ornés « -= … =- ».**

- Le logo d'un label est pris d'office sur Discogs (jeton DISCOGS_TOKEN) à la première visite de sa page ; un
  administrateur peut le changer ou le retirer.
- Page d'un artiste : les intertitres de catégorie prennent la forme des pastilles d'années (« Albums 3 ») ; sous
  chaque apparition, l'artiste précède les titres (« Axwell - Feel The Vibe »).
- Un nom de release qui porte le tag RADIO est rangé dans Live & Radio.
- Les dossiers encadrés de « -= … =- » (« -= Tomorrowland 2013 =- ») ont pour titre leur nom sans l'ornement : leur
  série devient « Tomorrowland ».

## [1.66.3](https://github.com/djkix/mp3-scene/compare/v1.66.2...v1.66.3) (2026-11-23)

### Résumé

**Photo d'artiste automatique, « Various Artists » en toutes lettres, fusion d'artistes plus simple.**

- La photo d'un artiste est prise d'office à la première visite de sa page : la première photo Deezer à son nom
  exact. Un administrateur peut la changer ou la retirer (elle n'est alors pas remise).
- « VA » s'affiche « Various Artists » (titre de la page, liste des artistes, fiche, pastilles) ; la base et les
  adresses gardent « VA ».
- Administration › Règles : la rubrique devient « Fusionner des artistes » et propose les noms pendant la frappe.

## [1.66.2](https://github.com/djkix/mp3-scene/compare/v1.66.1...v1.66.2) (2026-11-23)

### Résumé

**Pochette remplacée visible tout de suite, liens sous le chemin, série dans le bloc d'informations.**

- Une pochette ajoutée, remplacée ou retirée s'affiche aussitôt : le navigateur revalide les pochettes et les
  vignettes au lieu de les garder une journée.
- Sur la fiche, un picto dossier précède le chemin ; les liens Discogs, Beatport et YouTube passent dessous.
- La barre de série sous les boutons disparaît : la ligne Série du bloc d'informations mène au volume précédent et au
  suivant.

## [1.66.1](https://github.com/djkix/mp3-scene/compare/v1.66.0...v1.66.1) (2026-11-23)

### Résumé

**Série sur la fiche d'une release, écoutes sans date.**

- La fiche indique la série de la release (au moins deux volumes), avec un lien vers sa page.
- La ligne Écoutes ne donne plus que le nombre.

## [1.66.0](https://github.com/djkix/mp3-scene/compare/v1.65.0...v1.66.0) (2026-11-23)

### Résumé

**Chapitres lus dans la tracklist des NFO, familles de séries par début de nom, catégories démarquées sur la page
d'un artiste.**

- **Chapitres** : sans fichier .cue, la tracklist minutée du NFO (« 1. Artiste - Titre 4:00 », « [00:00] … ») devient
  les chapitres des longs mixes, un disque par piste, quand elle tient dans leur durée.
- **Familles de séries** : une règle qui rattache un nom à lui-même (« Kontor » → « Kontor ») réunit toutes les séries
  qui commencent par ce nom.
- **Page d'un artiste** : un intertitre (« Albums · 3 ») et un liseré de couleur marquent chaque catégorie ; sous
  chaque apparition, les titres de l'artiste dans la release.
- **Recherches** : le nombre de disques collé au titre (« Mystery Land 2010-2CD ») n'est plus envoyé aux recherches de
  pochettes ni aux liens Discogs, Beatport et YouTube.
- **Fiche** : les cartes des autres versions et des releases similaires donnent genre, catégorie, pistes, débit,
  poids, puis date.

## [1.65.0](https://github.com/djkix/mp3-scene/compare/v1.64.0...v1.65.0) (2026-11-23)

### Résumé

**Familles de genres, recherche dans les NFO, photo d'artiste, compteur d'écoutes, règles de familles de séries.**

- **Genres** : un genre dont le dernier mot est lui-même un genre le rejoint (« Deep House », « Tech House » dans
  House). La page d'un genre montre un bloc par genre de sa famille et le même en-tête que celle d'un label.
- **Recherche dans les NFO** : un onglet « NFO » de la recherche trouve les releases par le texte de leur NFO, indexé
  au scan (et au premier démarrage de cette version).
- **Photo d'artiste** : un administrateur peut en choisir une parmi celles proposées (Deezer) ; elle s'affiche sur la
  page de l'artiste.
- **Écoutes** : la fiche d'une release indique combien de fois elle a été écoutée et quand pour la dernière fois ;
  les listes se trient par nombre d'écoutes.
- **Familles de séries** (Administration › Règles) : rattacher une série à une famille, la garder à part, ou défaire
  une famille.
- **Page d'un artiste** : ses releases s'ouvrent groupées par catégorie — albums, singles, compilations, live.

## [1.64.0](https://github.com/djkix/mp3-scene/compare/v1.63.0...v1.64.0) (2026-11-23)

### Résumé

**Séries regroupées par famille, page d'une série avec filtres et en-tête.**

- **Familles** : les séries qui partagent leur début (« Hed Kandi Beach House », « Hed Kandi Nu Cool »…) ne font
  plus qu'une ligne dans l'onglet Séries, avec leur nombre. Sur la page de la famille, un bloc par série, comme pour
  les catégories : un clic s'y limite, un second revient à l'ensemble.
- **Page d'une série** : mêmes onglets et mêmes filtres (Genre, Années, texte) que la liste des séries, et un en-tête
  en deux colonnes — séries, releases, poids, détail par catégorie et années à gauche ; genres, labels et volumes
  absents à droite. Les chiffres portent sur ce qui est affiché.

## [1.63.0](https://github.com/djkix/mp3-scene/compare/v1.62.0...v1.63.0) (2026-11-23)

### Résumé

**Liens externes et chemin sur la fiche, contrôle « Sans genre », versions côte à côte, en-tête des labels et des groupes.**

- **Fiche** : le chemin du dossier dans la bibliothèque, avec un bouton pour le copier, et trois liens qui cherchent
  la release sur Discogs, Beatport et YouTube.
- **Sans genre** : nouveau contrôle qualité. « Proposer des genres » donne à chaque release le genre le plus fréquent
  de son artiste, à défaut de son label, quand il est net ; le nombre et des exemples sont montrés avant d'appliquer.
- **Comparer** : depuis « Autres versions », un tableau met les versions côte à côte (groupe, source, pistes, débit,
  taille, NFO, liste des pistes), le meilleur débit en évidence.
- **Labels et groupes** : leur page reçoit le même en-tête que celle d'un artiste (releases, poids, années, artistes,
  genres, groupes ou labels associés).
- **Artistes des pistes** : ceux qui ne diffèrent que par la casse (« AXWELL », « Axwell ») prennent la graphie la plus
  fréquente.

## [1.62.0](https://github.com/djkix/mp3-scene/compare/v1.61.0...v1.62.0) (2026-11-23)

### Résumé

**Remixes d'un artiste, pochettes automatiques.**

- **Remixes** : la page d'un artiste gagne une ligne « Remixes », les pistes dont le titre le crédite d'une version
  (« Crazy (Axwell Remix) », « … [Axwell & X Dub] »), où qu'elles soient dans la bibliothèque.
- **Pochettes automatiques** (contrôle qualité « Sans pochette ») : pour chaque release, la première proposition au
  même artiste et au même titre est validée sans rien demander ; les autres releases restent à voir à la main.

## [1.61.0](https://github.com/djkix/mp3-scene/compare/v1.60.1...v1.61.0) (2026-11-23)

### Résumé

**Accès direct depuis la recherche, rapprochements suggérés, volumes à compléter, BPM et tonalité, cache de conversion.**

- **Recherche** : au-dessus des résultats, les artistes, labels et séries dont le nom contient les mots cherchés
  (cinq de chaque, avec leur nombre de releases) ; un clic ouvre leur page.
- **Rapprochements suggérés** (Administration › Règles) : labels et artistes qui ne diffèrent que par « & » / « and »,
  un mot final de label (« Productions », « Digital »…) ou un « The » / « DJ » initial, à rattacher d'un clic.
- **Volumes à compléter** : depuis l'onglet Séries, le tableau des séries où il manque des numéros, avec la liste à
  copier.
- **BPM et tonalité** : lus au scan avec les autres tags, affichés sur la fiche d'une release et dans les listes de
  pistes ; filtre par plage de BPM sur l'onglet Pistes de la recherche. Les pistes indexées avant cette version les
  reçoivent par « Relire tous les tags » (Administration › Scan).
- **Cache de conversion** : sa taille figure dans la vue d'ensemble, avec un bouton pour le vider.
- **Artistes** : un tag qui ajoute une mention à l'artiste du nom (« Daft Punk - Live », « Daft Punk [BMi D0MiNAti0N] »)
  ne crée plus un artiste à part.

## [1.60.1](https://github.com/djkix/mp3-scene/compare/v1.60.0...v1.60.1) (2026-11-23)

### Résumé

**Fréquence d'échantillonnage sur la fiche d'une release.**

- La fiche affiche de nouveau la fréquence (« 44,1 kHz »), après le débit : sur une release sans source ni label,
  les deux colonnes du bloc ont le même nombre de lignes. Elle est lue dans le fichier de la première piste.

## [1.60.0](https://github.com/djkix/mp3-scene/compare/v1.59.1...v1.60.0) (2026-11-23)

### Résumé

**Page d'un artiste : un tableau des quatre listes à la place des onglets.**

- Le bloc de gauche devient un tableau : Releases, Avec, Apparitions et Mixes, chacune avec son nombre et son
  poids. Un clic sur une ligne ouvre sa liste, la ligne ouverte est marquée ; les quatre onglets disparaissent.
- L'en-tête (tableau, labels, artistes associés, releases les plus écoutées) reste affiché sur les quatre listes.
- Les lignes par catégorie et les années d'activité quittent le bloc : le filtre Catégories et les pastilles
  d'années les donnent toujours.

## [1.59.1](https://github.com/djkix/mp3-scene/compare/v1.59.0...v1.59.1) (2026-11-23)

### Résumé

**En-tête de la page d'un artiste en deux colonnes.**

- À gauche, un tableau : releases, poids, une ligne par catégorie (un clic filtre la liste), années d'activité. À
  droite, les labels, les artistes associés et les releases les plus écoutées, en pastilles cliquables. Sur mobile,
  les deux colonnes passent l'une sous l'autre.
- Les graphies d'un même label (« Bits & Pieces », « Bits And Pieces ») y sont réunies ; les releases les plus
  écoutées sont montrées par leur titre.

## [1.59.0](https://github.com/djkix/mp3-scene/compare/v1.58.0...v1.59.0) (2026-11-23)

### Résumé

**Onglet Séries, autres versions d'un morceau, fiche d'artiste enrichie, pas de fondu dans une même release.**

- **Séries** : nouvel onglet d'Explorer, qui liste les séries d'au moins trois volumes (« Kontor Top Of The Clubs »,
  « Serious Beats »…) avec leur nombre de releases et leur poids ; un clic ouvre la page de la série, ses volumes
  dans l'ordre et les numéros absents.
- **Autres versions** : dans le menu d'une piste, la liste des pistes du même artiste et du même titre (remixes,
  edits, la même piste sur une autre release), le meilleur débit d'abord ; un clic lit la version choisie.
- **Artiste** : sa page indique ses années d'activité dans la bibliothèque, ses labels, les artistes avec qui il
  signe le plus de pistes et ses releases les plus écoutées.
- **Fondu enchaîné** : deux pistes d'une même release s'enchaînent sans fondu, pour ne pas abîmer un album ou une
  compilation mixée.

## [1.58.0](https://github.com/djkix/mp3-scene/compare/v1.57.1...v1.58.0) (2026-11-23)

### Résumé

**Titres mieux lus dans les noms de release, synthèse par catégorie sur l'onglet Pistes de la recherche.**

- **Titres** : un dernier segment qui n'a pas la forme d'un groupe reste dans le titre (« VA-La_Rocca_-_Ballroom_Tunes_6 »
  donne « La Rocca - Ballroom Tunes 6 », « Live At La Rocca (08-06-06) » n'est plus coupé à « (08-06 »). Après « VA- »,
  le premier tiret sépare l'artiste du titre : « VA-Buddha-Bar_IX_-_By_Ravin » n'a plus l'artiste « VA-Buddha-Bar IX ».
  Une compilation « titre - mixed by X » est rangée sous VA, avec son nom complet pour titre.
- Les releases déjà en base sont relues au démarrage, sauf celles dont l'artiste ou le titre a été corrigé à la main.
- **Recherche** : l'onglet Pistes affiche la même ligne que l'onglet Releases, le nombre de pistes et leur poids par
  catégorie, un clic filtrant sur la catégorie.
- **Détails techniques** : la ligne « Canaux » est retirée, le format suffit.

## [1.57.1](https://github.com/djkix/mp3-scene/compare/v1.57.0...v1.57.1) (2026-11-22)

### Résumé

**Sous-dossiers numérotés reconnus comme des disques.**

- Un sous-dossier nommé d'un simple numéro (« 1 », « 2 », « 02 ») qui contient des pistes est lu comme un disque de
  la release parente, comme « CD1 » ou « Disc 2 ». Les releases « 1 », « 2 », « 3 » indexées jusque-là à part
  rejoignent leur album au scan suivant.

## [1.57.0](https://github.com/djkix/mp3-scene/compare/v1.56.0...v1.57.0) (2026-11-22)

### Résumé

**Synthèse par catégorie sur la recherche, débit sur la fiche, anneau des groupes.**

- **Recherche** : sous les onglets, le total des releases trouvées et leur détail par catégorie avec le poids
  (« 15 releases · 1,1 Go : 12 Compilations (894 Mo) · 3 Live & Radio (190 Mo) »). Un clic sur une catégorie filtre ;
  les chiffres suivent les filtres.
- **Fiche d'une release** : le débit moyen, après le format.
- **Statistiques** : un anneau « Par groupe » avec les autres anneaux (les cinq premiers groupes, puis « Autres ») ;
  les classements des releases et des pistes les plus écoutées n'ont plus de barres, le nom prend la largeur.

## [1.56.0](https://github.com/djkix/mp3-scene/compare/v1.55.0...v1.56.0) (2026-11-22)

### Résumé

**Statistiques par groupe.**

- Administration › Statistiques : un classement « Par groupe », les quinze groupes qui ont le plus de releases, avec
  leur nombre et leur poids.

## [1.55.0](https://github.com/djkix/mp3-scene/compare/v1.54.1...v1.55.0) (2026-11-22)

### Résumé

**Initiales sur la page Catégories, nom des compilations datées aligné sur leur série.**

- **Page Catégories** : la barre de lettres des artistes (Tous, #, A à Z) filtre les releases par initiale. Le « VA- »
  d'une compilation est ignoré, sinon elles seraient toutes sous V. La lettre suit quand un filtre change.
- **Compilations « année - série - titre »** de Ministry of Sound et Hed Kandi : leur nom affiché prend la forme du
  reste de la série (« 1995_-_Ministry_of_Sound_-_The_Annual_1_[2CD] » devient
  « VA-Ministry_of_Sound_The_Annual_1-2CD-1995 »). Seul le nom en base change, pas le dossier sur le disque.

## [1.54.1](https://github.com/djkix/mp3-scene/compare/v1.54.0...v1.54.1) (2026-11-22)

### Résumé

**Artiste encadré par un symbole décoratif.**

- Un artiste lu dans les tags et encadré par un même symbole (« ✖ Tristan Garner ✖ ») est débarrassé de ce symbole,
  à la lecture des fichiers et pour les données déjà en base. « A+ », « 200° » ou « Life+ » restent tels quels.

## [1.54.0](https://github.com/djkix/mp3-scene/compare/v1.53.2...v1.54.0) (2026-11-22)

### Résumé

**Compilations datées rangées avec leur série, artistes de balise vides de sens écartés, survol des lignes.**

- **Compilations « année - série - titre »** de Ministry of Sound et Hed Kandi (« 1999 - Hed Kandi - Nu Cool Vol. 2
  [2CD] ») : rangées comme le reste de leur série, avec l'artiste VA, l'année du nom, le label de la série et un
  titre complet (« Hed Kandi Nu Cool Vol. 2 »). Elles rejoignent ainsi les pages de série.
- **Artiste des tags vide de sens** (« [Notag] », « Artist », « No Artist », « Unknown », « Untitled », « Inconnu ») :
  écarté ; l'artiste lu dans le nom de la release le remplace. Une correction manuelle garde la priorité.
- **Groupes** : un dernier segment qui commence par un tiret bas (« …-_Ballroom_Tunes_6 ») est la fin d'un titre,
  pas un groupe ; la release est rangée dans P2P.
- **Survol** : sur ordinateur, la ligne sous le pointeur est surlignée dans tous les tableaux et dans la file
  d'attente, comme les pistes d'une fiche.
- **Fiche d'une release** : la fréquence est retirée, le format prend sa place et s'affiche sans attendre.

## [1.53.2](https://github.com/djkix/mp3-scene/compare/v1.53.1...v1.53.2) (2026-11-22)

### Résumé

**Format à la place des canaux, tableau des pistes resserré.**

- **Format** (MP3, FLAC…) à la place des canaux sur la fiche d'une release et dans le lecteur plein écran ; sur
  ordinateur, le lecteur l'affiche au-dessus du débit.
- **Tableau des pistes** : chaque colonne, sauf « Artiste - Titre », est centrée sous son libellé et réduite à son
  contenu ; la largeur va au titre.
- **Page d'un artiste** : le total (« 7 releases · 923 Mo ») passe sous les onglets, devant le détail par type.

## [1.53.1](https://github.com/djkix/mp3-scene/compare/v1.53.0...v1.53.1) (2026-11-22)

### Résumé

**Points médians entre les informations d'une release.**

- Sur les cartes de release (mobile, et cartes de la fiche à toute largeur), un point médian sépare le genre, la
  date, les pistes, le débit, le poids et la catégorie. Aucune ligne ne commence par un point.

## [1.53.0](https://github.com/djkix/mp3-scene/compare/v1.52.1...v1.53.0) (2026-11-22)

### Résumé

**Releases similaires pour les sets de festival, pictogrammes du lecteur, scan depuis la vue d'ensemble.**

- **Releases similaires** : le set d'un festival (« Festival_2025-DJ_Untel_Live-STREAM… ») n'en proposait aucune,
  son artiste connu étant le festival. La liste est maintenant complétée par les releases et les autres sets de
  celui qui joue, lu dans le nom avant « _Live », puis par le même genre, les années les plus proches d'abord.
  Toute fiche qui avait peu de propositions en reçoit ainsi jusqu'à douze.
- **Lecteur plein écran** : groupe en premier, puis source, débit, fréquence et canaux, chacun précédé d'un
  pictogramme ; les points de séparation disparaissent.
- **Administration** : le bloc Scan de la vue d'ensemble a son bouton « Lancer le scan » et suit l'état jusqu'à la fin.

## [1.52.1](https://github.com/djkix/mp3-scene/compare/v1.52.0...v1.52.1) (2026-11-22)

### Résumé

**Longs mixes FLAC et WAV sans attente, suite des retouches mobile.**

- **Longs mixes en FLAC et WAV** : à partir de 20 minutes, le fichier est envoyé tel quel quand le navigateur sait le
  lire. Sa conversion durait plus d'une minute et la lecture était abandonnée avant. Le fichier d'origine est lourd
  (de l'ordre de 1 Go par heure en FLAC).
- **Fiche sur mobile** : les cartes de « Autres versions » et de « Releases similaires » ne gardent plus un grand
  vide en bas (défaut de la 1.52.0) ; plus aucune valeur coupée dans le bloc d'informations.
- **Lecteur plein écran** : l'artiste sur une ligne, le titre dessous ; un titre trop long défile.
- **Petit lecteur** : barre de progression sous le titre, plus épaisse ; un appui déplace la lecture.
- **Contrôle qualité sur mobile** : les contrôles sont dans une liste déroulante, avec leur nombre.
- **Correction en lot** (cases à cocher, « Corriger la sélection », « Tout cocher ») : sur ordinateur seulement.

## [1.52.0](https://github.com/djkix/mp3-scene/compare/v1.51.0...v1.52.0) (2026-11-22)

### Résumé

**Mobile resserré, types d'un artiste, formats dans les statistiques.**

- **Page d'un artiste** : sous le nom, ses releases par type (« 10 Singles (214 Mo) · 4 Albums (65 Mo) ») ; un clic
  filtre la liste sur ce type.
- **Statistiques** : anneau « Pistes par format » (MP3, FLAC, M4A…) avec le nombre et le poids.
- **Autres versions** : une pastille « Garder cette version » à droite du titre remplace le bloc de boutons ; elle
  devient « Tout réafficher » quand des versions sont masquées.
- **Lignes de release** : un « i » cerclé remplace la flèche vers la fiche.
- **Mobile** :
  - filtres sur deux colonnes, « Réinitialiser » centré dessous, « Playlist auto » réservé à l'ordinateur ;
  - cartes de release : texte plus large, centré en hauteur face aux boutons ;
  - lecteur plein écran : fréquence et canaux, espace réparti autour des informations, boutons aléatoire et
    répétition du même trait que précédent et suivant ;
  - petit lecteur : titre et artiste centrés sur la pochette ;
  - file d'attente : texte plus grand, boutons resserrés ;
  - fiche : pochette centrée, tableau des pistes sans colonne playlist, un cœur pour l'en-tête « Favori » ;
  - réglages audio : explications repliées derrière des « ? » ;
  - administration : menu en liste déroulante.

## [1.51.0](https://github.com/djkix/mp3-scene/compare/v1.50.1...v1.51.0) (2026-11-22)

### Résumé

**Fichiers `.mp4` lus, recherche de pochettes Discogs plus large.**

- **Fichiers `.mp4`** : le scan les indexe comme des pistes et le lecteur en lit le son, sans conversion quand le
  navigateur sait lire le format (le fichier entier est envoyé, image comprise). Ils apparaissent au scan suivant.
- **Recherche de pochettes sur Discogs** : quand le titre exact ne donne rien, un second essai est fait sans son suffixe
  (« … EP », « …-(Remixes) »), puis avec la référence de catalogue lue entre parenthèses dans le nom du dossier
  (« (BL-16188-X) »).

## [1.50.1](https://github.com/djkix/mp3-scene/compare/v1.50.0...v1.50.1) (2026-11-22)

### Résumé

**Longs mixes en M4A lus sans attente.**

- Un long mix en M4A ne démarrait pas : sa conversion en MP3 durait plus d'une minute et la lecture était abandonnée
  avant. Les fichiers M4A, OGG et Opus sont maintenant envoyés tels quels quand le navigateur sait les lire. FLAC et
  WAV restent convertis, sauf avec le réglage « qualité d'origine ».

## [1.50.0](https://github.com/djkix/mp3-scene/compare/v1.49.1...v1.50.0) (2026-11-21)

### Résumé

**Recherche de pochettes : Discogs à la place de Brave.**

- La recherche d'images Brave (`BRAVE_API_KEY`), qui demandait une carte bancaire, est retirée.
- Avec `DISCOGS_TOKEN` (jeton personnel d'un compte Discogs gratuit, Paramètres › Développeurs), les pochettes sont
  cherchées aussi sur Discogs, en plus de Deezer et d'iTunes. Sans jeton, rien ne change.
- Seuls l'artiste et le titre de la release sont envoyés à ces services.

## [1.49.1](https://github.com/djkix/mp3-scene/compare/v1.49.0...v1.49.1) (2026-11-21)

### Résumé

**Releases similaires de nouveau affichées sous le NFO.**

- Le bloc « Releases similaires » d'une fiche ne s'affichait plus dès que deux releases ou plus étaient proposées
  (défaut présent depuis la 1.35.0, devenu visible partout avec les propositions par série et par label).

## [1.49.0](https://github.com/djkix/mp3-scene/compare/v1.48.0...v1.49.0) (2026-11-21)

### Résumé

**Recherche de pochettes, fréquence et canaux sur la fiche, fenêtres fermées d'un clic à côté.**

- **Recherche de pochettes** (administrateur) : Administration › Contrôle qualité › Sans pochette › « Chercher les
  pochettes » passe les releases une par une et propose des images ; un clic sur une image la valide, « Passer » va à
  la suivante. Le même bouton existe sur la fiche d'une release (« Chercher une pochette »). L'image validée est gardée
  comme une pochette déposée à la main : rien n'est écrit dans le dossier de musique.
- Les images viennent de Deezer et d'iTunes, sans clé. Avec `BRAVE_API_KEY` (clé de l'API Brave Search), une
  recherche d'images sur le web s'y ajoute, utile pour les lives et les émissions de radio. Seuls l'artiste, le titre
  et l'année de la release sont envoyés à ces services. Le serveur ne télécharge que les images qu'il a lui-même
  proposées (adresse signée, https, hôte public, 8 Mo au plus).
- **Fiche d'une release** : fréquence d'échantillonnage et canaux dans les détails ; les pastilles non cliquables sont
  grises ; les colonnes Playlist, Favori et Télécharger (MP3) ont un libellé au-dessus des pistes.
- **Fenêtres** : un clic ou un appui en dehors d'une fenêtre la ferme, sur ordinateur comme sur mobile.

## [1.48.0](https://github.com/djkix/mp3-scene/compare/v1.47.1...v1.48.0) (2026-11-20)

### Résumé

**Page d'une série, volumes absents, mixes où figure un artiste.**

- **Page d'une série** (`#/series/<nom>`) : tous les volumes d'une série (« Global Underground », « Kontor Top Of The
  Clubs »…) dans l'ordre de leur numéro. Sur la fiche d'une release, une ligne mène au volume précédent, à la page de
  la série et au volume suivant.
- **Volumes absents** : la page d'une série indique les numéros qui manquent entre le plus petit et le plus grand
  volume présents, à partir de trois volumes. Rien pour une série datée (« Hed Kandi 2005 ») ni au-delà de 60 trous.
- **Onglet « Mixes » d'un artiste** : les longs mixes où un chapitre (fichier `.cue`) est de lui ; un clic lance la
  piste à son morceau.
- « Vol », « Volume », « Issue », « Part » en fin de nom de série sont ignorés : « … Vol 63 » et « … 64 » forment la
  même série, y compris pour les releases proposées en bas de fiche.

## [1.47.1](https://github.com/djkix/mp3-scene/compare/v1.47.0...v1.47.1) (2026-11-20)

### Résumé

**Releases proposées sous une compilation.**

- Une compilation (artiste « VA ») n'avait souvent aucune release similaire. Elle propose maintenant celles de la même
  série, reconnue au début du titre avant son numéro (« Global Underground 47… »), puis celles du même label, avant le
  même genre la même année.

## [1.47.0](https://github.com/djkix/mp3-scene/compare/v1.46.0...v1.47.0) (2026-11-20)

### Résumé

**Chapitre en cours dans le lecteur, recherche dans les chapitres, reprise des longs mixes.**

- Lecteur : le morceau en cours d'un long mix s'affiche à droite de la barre (au-dessus des outils en plein écran),
  avec « chapitre précédent » et « chapitre suivant ».
- Recherche, onglet Pistes : un morceau joué dans un mix est trouvé par son chapitre ; un clic lance le mix à cet
  endroit. Les fichiers `.cue` sont lus pendant le scan et gardés en base : un scan est nécessaire après la mise à jour.
- Longs mixes (plus de vingt minutes) : la position d'écoute est gardée par compte ; au lancement suivant, un bouton
  propose de reprendre là où l'écoute s'était arrêtée.
- Favoris › Statistiques : chiffres clés, courbe des écoutes par jour et anneau des genres.
- Fiche : pastilles toutes de la même couleur ; cœur de la barre d'actions identique à celui des pistes.

## [1.46.0](https://github.com/djkix/mp3-scene/compare/v1.45.0...v1.46.0) (2026-11-20)

### Résumé

**Chapitres des longs mixes, détails techniques, chronologie d'un artiste, journal d'activité.**

- Fiche : section **Chapitres** pour les pistes accompagnées d'un fichier `.cue` (heure, artiste, titre) ; un clic
  lance la piste à cet endroit.
- Menu « … » d'une piste : **Détails techniques** lus dans le fichier (format, débit et son mode, fréquence, canaux,
  encodeur, tags, BPM et tonalité quand ils existent).
- Page d'un artiste : une pastille par année avec le nombre de releases ; un clic filtre la liste.
- Administration › **Journal** : connexions, actions d'administration, sauvegardes et écoutes de tous les comptes,
  le plus récent d'abord ; 20 000 lignes gardées.

## [1.45.0](https://github.com/djkix/mp3-scene/compare/v1.44.0...v1.45.0) (2026-11-20)

### Résumé

**Qualité d'origine, pochette ajoutée à la main, chiffres exacts sur les graphiques.**

- Lecteur : réglage **Qualité d'origine** (par appareil) ; les FLAC, WAV, M4A, OGG et Opus que le navigateur sait lire
  sont envoyés tels quels au lieu d'être convertis en MP3. WMA, APE et WavPack restent convertis.
- Fiche (administrateur) : **Ajouter une pochette**, gardée dans `data/covers`, jamais dans le dossier de musique ;
  elle passe avant celle du dossier et est copiée par la sauvegarde.
- Statistiques : nombre exact, poids et pourcentage dans la légende des anneaux ; valeur du point survolé ou touché
  sous la courbe et les colonnes.
- Pistes : un artiste coupé à 30 caractères est complété par le nom du fichier, comme les titres ; la recherche trouve
  un mot de la partie complétée.

## [1.44.0](https://github.com/djkix/mp3-scene/compare/v1.43.0...v1.44.0) (2026-11-20)

### Résumé

**Statistiques de l'administration en tableau de bord, avec graphiques.**

- Huit chiffres clés (bibliothèque, puis usage sur la période choisie), courbe des écoutes par jour, anneaux pour les
  catégories, les sources, les classes de débit et les genres écoutés, colonnes pour les releases par année et les
  ajouts par mois, classements en barres pour les artistes, releases, pistes et utilisateurs.
- Les graphiques sont dessinés par l'application (SVG), sans bibliothèque externe ; couleurs adaptées aux thèmes
  clair et sombre.

## [1.43.0](https://github.com/djkix/mp3-scene/compare/v1.42.0...v1.43.0) (2026-11-20)

### Résumé

**Statistiques d'usage dans l'administration, liens de fiche fiabilisés.**

- Administration › Statistiques : section **Usage**, tous comptes confondus, sur 7 jours, 30 jours, 12 mois ou depuis
  le début : écoutes par jour et par utilisateur, artistes, releases, pistes et genres les plus écoutés, avec le
  nombre d'écoutes et la durée.
- Corrigé : le lien vers la fiche d'une release dont le nom est tout en chiffres (« 1 ») ouvrait la release portant
  ce numéro ; deux releases de même nom ouvraient toujours la même. Les liens portent désormais l'identifiant.
- Favoris : cœur toujours plein, de la couleur du texte, vert quand l'élément est en favori.

## [1.42.0](https://github.com/djkix/mp3-scene/compare/v1.41.1...v1.42.0) (2026-11-20)

### Résumé

**Sauvegarde quotidienne de la base, ordre fixe des catégories.**

- Sauvegarde intégrée (facultative, `BACKUP_DIR`) : chaque jour à partir de `BACKUP_HOUR` (3 h par défaut), la base
  est copiée à chaud et vérifiée dans un dossier daté ; sept jours gardés, nuit manquée rattrapée, nouvelle tentative
  une heure après un échec. Le fichier compose et le `.env` sont copiés si le dossier de la pile est monté sur `/stack`.
- Administration › Vue d'ensemble : carte **Sauvegarde** (dernière réussite, dernière tentative, heure), alerte après
  36 heures sans réussite, bouton **Sauvegarder maintenant**.
- Catégories toujours dans l'ordre Singles, Albums, Compilations, Live & Radio.

## [1.41.1](https://github.com/djkix/mp3-scene/compare/v1.41.0...v1.41.1) (2026-11-20)

### Résumé

**Filtres sur l'onglet Pistes de la recherche.**

- L'onglet Pistes a les mêmes filtres que l'onglet Releases (Catégories, Genres, Années, Sources, à choix multiples,
  avec Réinitialiser) ; ils s'appliquent à la release de chaque piste et suivent d'un onglet à l'autre.

## [1.41.0](https://github.com/djkix/mp3-scene/compare/v1.40.1...v1.41.0) (2026-11-20)

### Résumé

**Catégories en blocs, genres ouverts dans Explorer, lecteur et cartes du téléphone retouchés.**

- Explorer › Catégories : un bloc par catégorie, centré au-dessus des filtres, et les releases dessous ; un second
  clic sur le bloc choisi revient à toutes les releases.
- Explorer › Genres : un genre ouvre ses releases dans Explorer (`#/genres/<nom>`) au lieu de la liste Derniers.
- Rattacher un artiste ou un label se fait dans Administration › Règles (formulaire au-dessus de chaque liste) ; le
  bouton a quitté les pages d'artiste et de label.
- Téléphone, cartes : les pictos sont empilés dans une colonne étroite, le nom gagne la largeur.
- Téléphone, lecteur : barre du bas avec le titre puis l'artiste ; en plein écran, pochette et forme d'onde agrandies
  selon la hauteur de l'écran ; seul le nom du groupe est en pastille.
- Le bouton Mix est retiré des listes.

## [1.40.1](https://github.com/djkix/mp3-scene/compare/v1.40.0...v1.40.1) (2026-11-20)

### Résumé

**Titres coupés à 30 caractères complétés par le nom du fichier.**

- Un titre de piste de 30 caractères exactement (limite des tags ID3v1) est complété à l'affichage par la suite lue
  dans le nom du fichier : « Always (Muthafunkaz Extended V » devient « Always (Muthafunkaz Extended Vocal mix) ».
  Sans correspondance dans le nom du fichier, ou si le titre est entier, rien ne change.

## [1.40.0](https://github.com/djkix/mp3-scene/compare/v1.39.1...v1.40.0) (2026-11-20)

### Résumé

**Listes de pistes au rendu des releases, filtres multiples dans Explorer, lecteur mobile et réglages audio retouchés.**

- Listes de pistes (recherche, favoris, historique, playlists) : même présentation que les releases, avec vignette,
  « Artiste - Titre », genre en pastille, durée, débit, release, menu « … » et cœur. La recherche de pistes est triée
  par titre.
- Explorer : filtres Genres et Années à choix multiples avec Réinitialiser ; Catégories a sa rangée de lettres.
- Lecteur : un titre trop long défile au lieu d'être coupé ; sur téléphone, la pochette suit le bandeau, le bouton de
  gauche est une flèche de retour et celui de droite un « i ».
- File d'attente : **Vider la file** garde la piste en cours, qui continue, et retire les autres.
- Réglages audio : une ligne par bande (nom, curseur, valeur), interrupteur pour le nivellement, boutons pour le fondu.
- Favoris : cœur de la couleur du texte, plein quand l'élément est en favori.
- Corrigé : « null » affiché sous « Autres versions » d'une fiche.

## [1.39.1](https://github.com/djkix/mp3-scene/compare/v1.39.0...v1.39.1) (2026-11-20)

### Résumé

**Menu déroulant pour les actions d'une piste.**

- Le bouton « … » d'une piste ouvre un menu sous le bouton (Lire ensuite, Ajouter à la file, Radio, playlists,
  Nouvelle playlist…) au lieu d'une boîte qui assombrit la page ; « Ajouter à une playlist » de la fiche utilise le
  même menu. Les playlists intelligentes n'y sont pas proposées.

## [1.39.0](https://github.com/djkix/mp3-scene/compare/v1.38.0...v1.39.0) (2026-11-20)

### Résumé

**Filtres à choix multiples, Catégories en tableau, fiche en pastilles.**

- Filtres des listes : Catégories, Genres, Années et Sources acceptent plusieurs choix (cases à cocher, appliquées à
  la fermeture de la liste) ; années et décennies s'additionnent. Bouton **Réinitialiser**. Mix et Playlist auto
  suivent ces choix.
- Explorer › Catégories : un tableau comme Artistes (catégorie, releases, poids) ; une catégorie ouvre la liste
  filtrée. Le navigateur de dossiers reste à l'adresse `#/folders`.
- Fiche : valeurs en pastilles colorées par type (provenance, classement, édition, mesures) ; la catégorie mène à sa
  liste et le catalogue au label ; le genre des pistes est en pastille.
- Fiche : actions centrées, dans l'ordre Lire, File, Playlist, Radio, Hors ligne, Favori, Télécharger, Partager ; le
  favori est un bloc comme les autres. Le bouton Corriger en est retiré (la correction reste possible par sélection).

## [1.38.0](https://github.com/djkix/mp3-scene/compare/v1.37.4...v1.38.0) (2026-11-20)

### Résumé

**Catégories devient un onglet d'Explorer.**

- Menu : « Catégories » n'y est plus ; il reste Derniers, Explorer, Favoris et Admin (ou Compte).
- Explorer : onglets dans l'ordre Artistes, Genres, Catégories, Labels, Groupes ; il s'ouvre sur Artistes.
- Les anciennes adresses `#/folders` fonctionnent toujours.

## [1.37.4](https://github.com/djkix/mp3-scene/compare/v1.37.3...v1.37.4) (2026-11-20)

### Résumé

**Labels : numéros de catalogue écartés, « Music » ignoré, rattachement manuel.**

- Un numéro de catalogue pris pour le label ou collé à lui est retiré (« ZYX 55786-2 », « ZYX82273-2 »,
  « BMG (74321-72236-2) ») ; une parenthèse qui répète le nom aussi (« Zyx Music (ZYX) »).
- « Music » final est ignoré au rapprochement, comme « Records » : « ZYX Music » rejoint « ZYX ».
- Quand la ligne du NFO nomme plusieurs labels (« EMI / Virgin »), seul le premier est gardé.
- Page d'un label (administrateur) : **Rattacher à…** réunit ce label à un autre ; Administration › Règles liste les
  labels rattachés. Détacher rend le label d'origine au scan suivant.

## [1.37.3](https://github.com/djkix/mp3-scene/compare/v1.37.2...v1.37.3) (2026-11-20)

### Résumé

**Labels nettoyés et réunis, navigation Admin en arborescence.**

- Labels : les restes de mise en forme du NFO sont retirés (« ..... Defected », « ] Deep State », « (Warner) »,
  « (P) 2014 Protocol Recordings ») ; « ? », « ..... » et une lettre seule ne sont plus des labels.
- Labels : les graphies qui ne diffèrent que par la casse, les accents, les espaces, la ponctuation ou un « Records »
  final sont réunies sous la plus répandue (« Spinnin », « Spinnin' Records », « SpinninRecords »). Appliqué à toute
  la base au démarrage.
- Administration : la colonne de navigation est une arborescence, rubriques en clair et liens en retrait avec un
  pictogramme chacun.

## [1.37.2](https://github.com/djkix/mp3-scene/compare/v1.37.1...v1.37.2) (2026-11-20)

### Résumé

**Une seule navigation Admin, vue d'ensemble qui ne reste plus bloquée, titre du lecteur centré.**

- Menu : pour un administrateur, « Compte » devient **Admin** et ouvre l'administration, dont la colonne de gauche
  réunit tout : Partages (Accès) et Mon compte (mot de passe, langue, thème, déconnexion) en sont des sections.
  Statistiques est rangé sous Bibliothèque. Un utilisateur garde sa page Compte.
- Contrôle qualité : le comptage des pistes illisibles prenait plusieurs minutes sur une grande bibliothèque et
  bloquait la vue d'ensemble ; il répond en quelques centièmes de seconde.
- Vue d'ensemble : chaque chiffre s'affiche dès que sa requête répond, au lieu d'attendre la plus lente.
- Lecteur (bureau) : titre et nom de la release centrés en hauteur sur la pochette.

## [1.37.1](https://github.com/djkix/mp3-scene/compare/v1.37.0...v1.37.1) (2026-11-20)

### Résumé

**Lecteur du bureau aéré, boutons en pastilles.**

- Barre du lecteur (bureau) : plus haute, de l'air entre le titre et la release et entre les boutons et la forme
  d'onde, pochette de 60 px.
- Boutons : chacun dans un rond de 40 px, lecture en rond vert plein de 52 px ; aléatoire, répéter, réglages audio et
  file sont des icônes dessinées. « Répéter une piste » porte un « 1 » en pastille.
- Le lecteur du téléphone ne change pas.

## [1.37.0](https://github.com/djkix/mp3-scene/compare/v1.36.0...v1.37.0) (2026-11-20)

### Résumé

**FLAC et autres formats convertis à l'écoute, labels, playlists intelligentes, version gardée d'un doublon,
artistes à ne jamais fusionner.**

- Formats : les pistes FLAC, WAV, M4A, WMA, OGG, Opus, AIFF, APE et WavPack sont indexées et converties en MP3
  320 kbit/s à l'écoute (`ffmpeg`, ajouté à l'image). La piste convertie est gardée dans `data/transcode` (5 Go au
  plus) ; le téléchargement donne le fichier d'origine. La première écoute attend la fin de la conversion.
- Labels : label et numéro de catalogue lus dans le NFO (à défaut, le numéro entre parenthèses du nom), affichés sur
  la fiche ; onglet **Labels** dans Explorer. Les NFO sont relus au prochain scan.
- Playlists intelligentes : sur une liste filtrée, **Playlist auto** enregistre les filtres ; la playlist suit la
  bibliothèque. Ni ordre manuel, ni retrait de piste, ni partage.
- Doublons : sur une fiche, **Garder cette version, masquer les autres** retire les autres versions des listes, de la
  recherche, d'Explorer et du Mix, sans rien supprimer du disque ; **Tout réafficher** annule.
- Artistes : Administration › Règles liste les graphies **à ne jamais fusionner** (« Florida » n'est pas
  « Flo Rida »).

## [1.36.0](https://github.com/djkix/mp3-scene/compare/v1.35.0...v1.36.0) (2026-11-20)

### Résumé

**Année dans les corrections, tout cocher, sélection sur la page d'un artiste, releases écoutées.**

- Corrections : la boîte **Corriger** a un champ Année, pour une release ou en lot ; un champ vidé revient à l'année
  du nom, sinon à celle du NFO.
- Contrôle qualité : **Tout cocher** sélectionne toutes les releases de l'onglet, même celles que le défilement n'a
  pas encore chargées (100 000 au plus par correction, contre 500).
- Page d'un artiste ou d'un groupe et recherche (administrateur) : cases à cocher et **Corriger la sélection**, pour
  sortir d'un artiste les releases qui y ont été rangées à tort.
- Favoris › Historique : choix **Pistes** / **Releases** ; les releases écoutées, la plus récente d'abord.

## [1.35.0](https://github.com/djkix/mp3-scene/compare/v1.34.0...v1.35.0) (2026-11-19)

### Résumé

**Correction en lot, rattachement manuel d'artistes, icônes du lecteur dessinées.**

- Contrôle qualité : des cases à cocher et **Corriger la sélection** donnent d'un coup le même artiste, la même
  catégorie ou le même genre à plusieurs releases (500 au plus) ; seuls les champs remplis sont modifiés.
- Page d'un artiste (administrateur) : **Rattacher à…** réunit cet artiste à un autre. La règle est gardée après les
  scans ; Administration › Règles liste les artistes rattachés et permet de les détacher.
- Lecteur : lecture, pause, précédent et suivant sont des icônes dessinées. C'étaient des caractères que certains
  téléphones, Android surtout, affichaient en emoji orange.
- Administration : sous 1100 px de large, la navigation passe en rangée au-dessus du contenu (la colonne écrasait le
  nom des releases du contrôle qualité).

## [1.34.0](https://github.com/djkix/mp3-scene/compare/v1.33.0...v1.34.0) (2026-11-19)

### Résumé

**Page Administration, pochette par défaut dans le lecteur, nouvelle icône de l'application.**

- Nouvelle page **Administration** (ouverte depuis Compte), rangée par type d'action : Vue d'ensemble, Bibliothèque
  (Scan, Contrôle qualité, Corrections), Classement (Règles), Accès (Utilisateurs, Partages), Système (Statistiques).
  Compte ne garde que ce qui concerne chaque utilisateur.
- **Scan quotidien** : une heure au choix (celle du serveur), ou jamais.
- **Corrections manuelles** : la liste des corrections en vigueur, avec retour à l'automatique.
- **Relancer le classement** sans redémarrer, et une page qui résume les règles.
- Contrôle qualité : nouvel onglet **Sans artiste**.
- Corrigé : un onglet actif survolé devenait illisible en thème sombre.

- Lecteur (bureau et téléphone) : une release sans image affiche une pochette par défaut, un disque vinyle
  « No embedded artwork ».
- Nouvelle icône : le même disque, avec « MP3Z / SCENE » en lettres de blocs ; favicon simplifié (disque seul).
  `scripts/make_icons.py` régénère les fichiers.

## [1.33.0](https://github.com/djkix/mp3-scene/compare/v1.32.0...v1.33.0) (2026-11-19)

### Résumé

**Lecteur plein écran du téléphone refait d'après la maquette.**

- Bandeau « En cours de lecture » avec réduire, Cast et un bouton vers la fiche de la release.
- Pochette plus grande, titre centré, nom de la release en pastille, ligne source · débit · groupe.
- Temps écoulé en vert sous la forme d'onde ; outils regroupés : DSP/EQ, **favori de la piste en cours**, file
  d'attente avec le nombre de pistes ; mention « Balayez pour changer de piste ».
- Le lecteur réduit du téléphone ne change pas.
- Barre du lecteur sur bureau : vignette même sans pochette, débit de la piste, volume en curseur horizontal
  (écrans d'au moins 1000 px), nombre de pistes en pastille sur le bouton de la file.
- Explorer : une rangée de lettres (Tous, #, A à Z) sous les filtres des onglets Groupes, Artistes et Genres limite
  la liste à une initiale.

## [1.32.0](https://github.com/djkix/mp3-scene/compare/v1.31.0...v1.32.0) (2026-11-19)

### Résumé

**Corrections manuelles d'une release, onglet « Avec » d'un artiste, année déduite du NFO.**

- Fiche : un administrateur peut **Corriger** l'artiste, la catégorie ou le genre d'une release. La correction est
  gardée après les scans ; un champ vidé revient à la valeur automatique.
- Page d'un artiste : nouvel onglet **Avec**, les releases dont le nom l'associe à un autre artiste (feat, vs, &),
  remixes compris.
- Une release sans année dans son nom prend celle de la date de son NFO.
- Fiche : artiste, source, date, catégorie, etc. sont alignés à droite de leur colonne au lieu d'être collés au libellé.

## [1.31.0](https://github.com/djkix/mp3-scene/compare/v1.30.2...v1.31.0) (2026-11-19)

### Résumé

**Artistes : les « vs » et les « & » rejoignent l'artiste principal.**

- « Daft Punk Vs Madonna » est rangé sous Daft Punk.
- « Chocolate Puma & Firebeatz » est rangé sous Chocolate Puma. Un duo reste entier tant qu'il a au moins autant de
  releases que son premier membre seul : Block & Crown, Dimitri Vegas & Like Mike, Above & Beyond ne bougent pas.
- Un artiste vide dans les tags (« . », « Unknown », « Unknown Artist ») laisse la place à celui du nom de la
  release ; « Various » et « Various Artists » deviennent VA.
- Un tag d'une ou deux lettres qui tronque l'artiste du nom (« A » pour A-Trak) est ignoré.

## [1.30.2](https://github.com/djkix/mp3-scene/compare/v1.30.1...v1.30.2) (2026-11-19)

### Résumé

**Artistes : une année seule devient VA.**

- Les compilations nommées « 2009 - Hed Kandi - … » avaient l'année pour artiste ; elles sont rangées sous VA.

## [1.30.1](https://github.com/djkix/mp3-scene/compare/v1.30.0...v1.30.1) (2026-11-19)

### Résumé

**Artistes : les espaces ne séparent plus deux graphies.**

- « 2ManyDJs » et « 2 Many DJs », « Fat Boy Slim » et « Fatboy Slim », « W&W » et « W & W » sont réunis.

## [1.30.0](https://github.com/djkix/mp3-scene/compare/v1.29.1...v1.30.0) (2026-11-19)

### Résumé

**Artistes regroupés : casse, ponctuation et featuring.**

- Les artistes des releases qui ne diffèrent que par la casse, les accents, les points, les apostrophes, les
  soulignés ou « and » / « & » sont réunis sous la graphie la plus répandue (« daft punk », « Daft_Punk » → Daft
  Punk ; « Block And Crown » → Block & Crown ; « Tiësto » → Tiesto).
- Un featuring rejoint l'artiste principal : « Zedd Feat Bright Lights » → Zedd. Les artistes des pistes ne changent
  pas.
- Le regroupement est refait à chaque scan et au démarrage ; la page Artistes et les « Autres versions » en profitent.
- Un nom en « VA- » avec un tag DVB, DVBC, DVBS, DVBT ou SBD (« VA-TMF_Yearmix-DVB-2007 ») reste dans Compilations.

## [1.29.1](https://github.com/djkix/mp3-scene/compare/v1.29.0...v1.29.1) (2026-11-19)

### Résumé

**Live & Radio : les émissions datées et les captations DVB ou SBD y sont rangées.**

- Un nom qui porte une date complète (« Essential_Selection_Hotmix_12-31-1999 », « -25-07-2009- ») désigne une
  émission ou un set : la release va dans Live & Radio, sauf compilation, CD ou tag de single.
- Les tags DVB, DVBC, DVBS, DVBT et SBD comptent comme SAT, CABLE ou FM.

## [1.29.0](https://github.com/djkix/mp3-scene/compare/v1.28.1...v1.29.0) (2026-11-19)

### Résumé

**La colonne Date montre la date de sortie lue dans le NFO.**

- La date d'une release est celle que son NFO annonce (date de release, sinon de rip, de diffusion, puis de mise en
  vente) ; sans NFO ou sans date lisible, la date d'ajout reste affichée. Elle figure aussi sur la fiche.
- Les NFO sont lus par le scan ; ceux des releases déjà en base le sont en tâche de fond au premier démarrage.
- Trier par Date suit la date affichée ; l'accueil « Derniers » reste classé par date d'ajout.

## [1.28.1](https://github.com/djkix/mp3-scene/compare/v1.28.0...v1.28.1) (2026-11-19)

### Résumé

**Albums : l'année 2012 n'est plus prise pour un maxi 12 pouces.**

- Le tag « 12 » (maxi vinyle) était reconnu dans l'année « 2012 » : les albums de 2012 restaient en Singles. Seuls
  « 12 » et « 2x12 » isolés comptent désormais ; les releases concernées sont reclassées au démarrage.

## [1.28.0](https://github.com/djkix/mp3-scene/compare/v1.27.2...v1.28.0) (2026-11-19)

### Résumé

**Autres versions d'une release, filtres Source et décennie, apparitions d'un artiste, catégories sans mélange.**

- Fiche : **Autres versions** liste, sous les pistes, les releases de même artiste et de même titre (autre groupe,
  autre source, réédition), avec leur débit et leur nombre de pistes pour comparer.
- Contrôle qualité : nouvel onglet **Doublons possibles**, toutes les releases qui ont une autre version.
- Listes : nouveau filtre **Sources** (WEB, VINYL, CDM, CDS…) ; le filtre Années propose aussi les **décennies**.
  La source de la fiche mène à la liste filtrée.
- Page d'un artiste : onglet **Apparitions**, les releases d'un autre artiste (compilations surtout) où il signe
  une piste.
- Onglet Catégories : un dossier ne montre plus que les releases de sa catégorie (les albums et les lives rangés
  avec les singles n'y figurent plus) ; le lien **Toute la catégorie** donne la liste complète.

## [1.27.2](https://github.com/djkix/mp3-scene/compare/v1.27.1...v1.27.2) (2026-11-19)

### Résumé

**Albums apparaît dans l'onglet Catégories.**

- La catégorie Albums, qui n'a pas de dossier, est listée à la racine de l'onglet Catégories ; elle ouvre la liste
  des releases filtrée sur Albums.
- Dans les listes, la colonne Catégorie est centrée, comme les autres.

## [1.27.1](https://github.com/djkix/mp3-scene/compare/v1.27.0...v1.27.1) (2026-11-19)

### Résumé

**Albums : les singles à nombreuses versions et les concerts n'en sont plus.**

- Une release dont au moins 60 % des pistes sont des versions d'un même morceau (« Crazy (Radio Edit) », « Crazy
  (Club Mix) »…) reste un single, quel que soit le nombre de pistes.
- « Concert » dans le nom compte comme « Live » : la release passe en Live & Radio (sauf VA ou indication de CD).

## [1.27.0](https://github.com/djkix/mp3-scene/compare/v1.26.1...v1.27.0) (2026-11-19)

### Résumé

**Nouvelle catégorie : Albums.**

- Une release du dossier des singles est rangée dans **Albums** quand elle compte au moins dix pistes et que son nom
  ne porte aucun tag de single (CDM, CDS, CDR, VINYL, EP, PROMO, BOOTLEG, Remixes, Mixes…). La catégorie apparaît dans
  le filtre, la colonne, la fiche et le tableau de bord.
- Albums n'a pas de dossier à elle : l'onglet Catégories montre toujours ces releases dans Singles.

## [1.26.1](https://github.com/djkix/mp3-scene/compare/v1.26.0...v1.26.1) (2026-11-19)

### Résumé

**Catégorie : « Live » verbe dans un titre ne fait plus un live.**

- « Live_And_Learn », « How_Can_I_Live_Without_You », « Sleep_Less_Live_More » ne rangent plus la release dans
  Live & Radio : elle garde la catégorie de son dossier.

## [1.26.0](https://github.com/djkix/mp3-scene/compare/v1.25.0...v1.26.0) (2026-11-19)

### Résumé

**Catégories : onglet renommé, catégorie déduite des tags. Noms de releases affichés avec des « _ ».**

- L'onglet et le fil d'Ariane s'appellent Catégories ; le premier niveau affiche Singles, Compilations et
  Live & Radio au lieu du nom des dossiers. Les sous-dossiers gardent leur nom, les adresses ne changent pas.
- La catégorie des lives s'appelle **Live & Radio** partout (colonne, filtre, fiche, tableau de bord).
- **Catégorie déduite des tags du nom**, à défaut seulement du dossier : un tag de diffusion (SAT, CABLE, DAB, FM,
  LINE) donne Live & Radio ; « VA » donne Compilations ; « Live » sans VA ni indication de CD donne Live & Radio ;
  CDS, CDM ou SINGLE donnent Singles. L'onglet Catégories, lui, montre toujours le rangement réel des dossiers.
- **Noms de releases** : à l'affichage, les espaces deviennent des « _ » (listes, fiche, lecteur), comme dans les
  noms de la scène. Les dossiers et les adresses ne changent pas.

## [1.25.0](https://github.com/djkix/mp3-scene/compare/v1.24.0...v1.25.0) (2026-11-19)

### Résumé

**Ordre alphabétique par défaut, hors derniers ajouts. Plus de place pour le nom des releases.**

- Les listes de groupes, d'artistes et de genres s'ouvrent triées par nom (et non plus par nombre de releases).
- Les releases d'un groupe, d'un artiste, d'un filtre (localisation, genre, année) ou d'une recherche s'ouvrent
  triées par nom. L'accueil sans filtre reste « derniers ajouts », du plus récent au plus ancien.
- Un clic sur un en-tête change toujours le tri.
- **Catégorie** remplace « Localisation » partout (colonne, filtre, fiche, tableau de bord). Dans les listes, la
  colonne affiche un libellé court : Singles, Compilations, Live.
- Sur ordinateur, les colonnes de la liste sont resserrées : le nom de la release gagne environ 200 pixels.

## [1.24.0](https://github.com/djkix/mp3-scene/compare/v1.23.0...v1.24.0) (2026-11-19)

### Résumé

**Groupes triés : ce qui n'est pas un groupe passe en P2P. Releases similaires après le NFO.**

- **P2P** : quand le dernier segment du nom n'a pas la forme d'un nom de groupe, la release est rangée dans P2P —
  bout de titre (espaces, crochets, parenthèses : « Clubbers Guide Summer [2CD] », « 06) »), source ou étiquette
  (WEB, VA, VINYL, CD1, 3CD, INT…), nombre d'un ou deux chiffres.
- **Noms abîmés réparés** : « WUS[rarbg] », « BPM.nz », « wWs.1 », « SOB_INT (1) » rejoignent WUS, BPM, wWs, SOB.
- Les groupes d'un seul mot sont gardés quelle que soit leur casse (UKHx, ZzZz, dh…).
- **Fiche** : les releases similaires sont affichées après le NFO.

## [1.23.0](https://github.com/djkix/mp3-scene/compare/v1.22.0...v1.23.0) (2026-11-19)

### Résumé

**Groupes : la casse ne sépare plus.**

- Les groupes qui ne diffèrent que par la casse (« dh » / « DH », « WITF » / « WiTF ») sont réunis sous la graphie
  la plus répandue, au démarrage puis à chaque scan.

## [1.22.0](https://github.com/djkix/mp3-scene/compare/v1.21.0...v1.22.0) (2026-11-19)

### Résumé

**Groupes : les releases internes rejoignent leur groupe, les releases sans groupe passent en P2P.**

- Le suffixe `_INT` (quelle que soit sa casse : `_iNT`, `_int`) est retiré du nom du groupe : « AOV_INT » et « AOV »
  ne font plus qu'un groupe, AOV. La base existante est corrigée au démarrage, les prochains ajouts à l'analyse de
  leur nom. Le nom de la release, lui, ne change pas.
- Quand le nom se termine par une année (« …-sat-02-12-2010 ») ou par « 320 » au lieu d'un groupe, la release est
  rangée dans le groupe **P2P** ; l'année est alors reprise comme année de la release si elle manquait.

## [1.21.0](https://github.com/djkix/mp3-scene/compare/v1.20.0...v1.21.0) (2026-11-19)

### Résumé

**Genres regroupés, localisations renommées.**

- **Genres** : les genres qui ne diffèrent que par l'orthographe, la casse ou la mise en forme sont regroupés
  (« house », « Hosue », « HOuse » → House ; « Club House » → Club-House ; « Drum_&_Bass » → Drum & Bass…). Une liste
  de genres (« House, Tech House, Deep House ») est réduite au premier. « Unknown », « Other », « Genre » et les
  adresses de sites deviennent « sans genre ». Les genres réellement différents (Disco, House) restent distincts.
- La base existante est regroupée au démarrage, les prochains ajouts à la lecture de leurs étiquettes. Les fichiers
  ne sont pas modifiés. La table de correspondance est dans `app/genres.py`.
- **Localisations** : les dossiers racine s'affichent sous un nom court — Singles, Compilations,
  Live / Cable / Sat / Radio — dans le filtre, la liste, la fiche et le tableau de bord.

## [1.20.0](https://github.com/djkix/mp3-scene/compare/v1.19.0...v1.20.0) (2026-11-18)

### Résumé

**Polices et icônes des maquettes, choix du thème, piste en cours mise en évidence, radio persistante.**

- **Polices** : Inter et JetBrains Mono sont embarquées dans l'application (sous-ensemble latin, 90 Ko au total,
  licence SIL OFL) ; plus rien ne dépend des polices installées sur l'appareil.
- **Icônes** : devant les onglets du bas sur téléphone et devant les actions de la fiche (Lire, Ajouter à la file,
  Radio, playlist, hors ligne, Partager, Télécharger).
- **Thème** : nouveau réglage dans Compte — Système, Clair ou Sombre. Le choix est gardé sur l'appareil.
- **Piste en cours** : sur la fiche et dans les listes de pistes (favoris, playlists, historique, recherche), la ligne
  qui joue porte un trait vert, son titre passe en vert et ▶ remplace son numéro.
- **Radio persistante** : la radio reprend après un rechargement de la page et sur un autre appareil. À chaque
  regarnissage, seules les vingt dernières pistes lues restent dans la file (sauf en lecture aléatoire).

## [1.19.0](https://github.com/djkix/mp3-scene/compare/v1.18.0...v1.19.0) (2026-11-18)

### Résumé

**Nouvel habillage, en clair et en sombre.**

- **Habillage** repris de maquettes : panneaux pour la barre du haut, les filtres, les en-têtes et le lecteur, filets
  fins, libellés en petites capitales à chasse fixe, entrée de navigation active en vert plein.
- **Liste** : genre en puce, débit en bleu, pastille « nouveau » avant le nom ; sur téléphone, chaque release est
  une carte.
- **Fiche** : informations dans un panneau sur deux colonnes, boutons d'action en capitales.
- **Lecteur** : bouton lecture en carré arrondi ; en plein écran sur téléphone, outils regroupés dans un panneau.
- Thème clair ou sombre selon le réglage du système, comme avant. Aucune police n'est téléchargée : Inter et
  JetBrains Mono sont utilisées si l'appareil les a, sinon les polices du système.

Aucune fonctionnalité n'est ajoutée ni retirée.

## [1.18.0](https://github.com/djkix/mp3-scene/compare/v1.17.0...v1.18.0) (2026-11-17)

### Résumé

**Radio : une file sans fin de pistes proches.**

- **Radio** : le bouton Radio de la fiche lit la release, puis enchaîne sans fin des pistes tirées au hasard dans
  les releases proches (même artiste, ou même genre à deux ans près). Le même bouton existe pour une piste, dans la
  boîte « Plus d'actions » (⋯). La file se regarnit quand il reste moins de cinq pistes à venir ; lancer une autre
  lecture ou vider la file arrête la radio, qui n'est pas non plus reprise après un rechargement de la page.
- **Descriptif pour maquette** (`docs/brief-design.md`) réécrit : il décrit toutes les fonctionnalités actuelles et
  liste ce que l'application ne fait pas.

## [1.17.0](https://github.com/djkix/mp3-scene/compare/v1.16.0...v1.17.0) (2026-11-17)

### Résumé

**Releases similaires sur la fiche et contrôle « sans pochette ».**

- **Releases similaires** : sous les pistes, la fiche propose jusqu'à douze releases proches — celles du même artiste
  d'abord, puis celles du même genre sorties la même année (le même groupe en tête). Les compilations (VA) ne sont
  rapprochées que par genre et année.
- **Contrôle « sans pochette »** (administrateur, Compte › Bibliothèque › Contrôle qualité) : releases sans image
  dans leur dossier ni dans les tags de leur première piste. La vérification se fait pendant le scan, et une fois
  pour toute la bibliothèque au premier démarrage de cette version : le compteur monte au fil de ce passage.

Une colonne est ajoutée à la base au démarrage : aucune migration manuelle.

## [1.16.0](https://github.com/djkix/mp3-scene/compare/v1.15.0...v1.16.0) (2026-11-16)

### Résumé

**Enchaînement sans blanc, fondu, égaliseur, liens de partage révocables, tableau de bord et contrôle qualité.**

- **Enchaînement sans blanc** : la piste suivante est préparée vingt secondes avant la fin et démarre à l'instant où
  la courante s'achève. Un **fondu enchaîné** de 2 à 12 secondes est réglable (indisponible sur iPhone, qui ne
  permet pas de régler le volume d'une page).
- **Réglages audio** (bouton ≋ du lecteur) : égaliseur graves, médiums, aigus, et nivellement du volume entre les
  pistes (un compresseur, pas une analyse piste par piste). Réglages gardés sur l'appareil. Sur iPhone, l'égaliseur
  et le nivellement peuvent couper le son écran verrouillé ; ils sont inactifs tant qu'ils restent à zéro.
- **Liens de partage** : la page Compte liste les liens en cours, avec leur échéance et leur nombre d'ouvertures, et
  permet de les copier ou de les révoquer. Les liens créés avec la 1.15.0 restent valables jusqu'à leur échéance
  mais n'apparaissent pas dans la liste.
- **Tableau de bord** (administrateur, Compte › Bibliothèque) : totaux, ajouts par mois, répartition par année,
  genre, source, localisation et débit.
- **Contrôle qualité** (administrateur) : releases sans NFO, sans tags, avec des pistes illisibles, à débit inférieur
  à 192 kbit/s, sans année ou sans piste. Pas de contrôle « sans pochette » : il faudrait relire chaque dossier du NAS.

Une table est créée au démarrage (liens de partage) : aucune migration manuelle.

## [1.15.0](https://github.com/djkix/mp3-scene/compare/v1.14.0...v1.15.0) (2026-11-16)

### Résumé

**File et playlists réordonnables, mix aléatoire, nouveautés, partage, minuterie, raccourcis.**

- **File d'attente** : boutons ▲ ▼ pour changer l'ordre, « Enregistrer » pour en faire une playlist. Le bouton ⋯
  d'une piste propose « Lire ensuite », « Ajouter à la file » et l'ajout à une playlist.
- **Playlists** : ordre modifiable (▲ ▼), bouton « Garder hors ligne » (aussi sur les pistes favorites) et « Partager ».
  Une playlist gardée hors ligne est une copie à l'instant du clic : les pistes ajoutées ensuite ne sont pas téléchargées.
- **Mix** : le bouton Mix des listes lance 50 pistes au hasard parmi les releases qui passent les filtres affichés
  (toute la bibliothèque, un genre, une année, un groupe, un artiste).
- **Nouveautés** : les releases ajoutées depuis la visite précédente portent une pastille « nouveau », et Derniers
  affiche leur nombre. Mémorisé par appareil.
- **Partage** : « Partager » sur une release ou une playlist copie un lien valable 7 jours, écoutable sans compte
  (page avec la liste des pistes et un lecteur). Le lien ne peut pas être révoqué avant son échéance.
- **Minuterie de sommeil** dans la file d'attente : 15, 30, 60 minutes ou fin de la piste.
- **Raccourcis clavier** : N et P (piste suivante, précédente), M (couper le son), / (recherche), en plus d'Espace et ← →.

## [1.14.0](https://github.com/djkix/mp3-scene/compare/v1.13.0...v1.14.0) (2026-11-16)

### Résumé

**Écoute hors ligne et reprise sur un autre appareil.**

- **Hors ligne** : le bouton « Garder hors ligne » de la fiche copie les pistes d'une release dans le stockage du
  navigateur. Ces pistes se lisent ensuite sans réseau, y compris en ouvrant l'application sans connexion : elle
  affiche alors la liste des releases gardées. La liste est aussi dans Favoris › Hors ligne, avec la place occupée.
  Se déconnecter efface ces copies. Nécessite HTTPS ; le système peut vider ce stockage s'il manque de place.
- **Reprise entre appareils** : la file, la piste et la position sont enregistrées sur le serveur, par compte. En
  ouvrant l'application ailleurs (ou en y revenant), on retrouve ce qu'on écoutait, en pause au même endroit. Rien
  n'est repris pendant une lecture en cours ; le dernier appareil utilisé fait foi.

Une table est créée au démarrage : aucune migration manuelle.

## [1.13.0](https://github.com/djkix/mp3-scene/compare/v1.12.1...v1.13.0) (2026-11-16)

### Résumé

**Playlists, recherche par piste, statistiques d'écoute, pages Artistes et Genres.**

- **Playlists** : listes de pistes nommées, propres à chaque utilisateur (Favoris › Playlists). Le bouton ♫ ajoute une
  piste depuis la fiche d'une release, une liste de pistes ou les résultats de recherche ; « Ajouter à une playlist »
  ajoute une release entière. Une playlist se lit, se renomme et se supprime ; une piste n'y figure qu'une fois.
- **Recherche par piste** : la recherche a un onglet Pistes, qui cherche dans le titre et l'artiste des tags (utile
  pour retrouver un morceau dans une compilation).
- **Statistiques** (Favoris › Statistiques) : nombre d'écoutes, durée écoutée, et les dix pistes, artistes, genres et
  groupes les plus écoutés, sur 7 jours, 30 jours, 12 mois ou tout l'historique.
- **Explorer** : l'entrée Groupes devient Explorer, avec trois onglets — Groupes, Artistes, Genres — chacun avec le
  nombre de releases et le poids. Au-delà de 1000 lignes, la liste demande d'affiner le filtre.
- **Fiche release** : l'artiste, l'année, le groupe et le genre sont des liens vers la liste correspondante.
- Sur téléphone, le téléchargement piste par piste est masqué dans la fiche (le zip reste disponible).

Deux tables sont créées au démarrage (playlists) : aucune migration manuelle, aucun scan.

## [1.12.1](https://github.com/djkix/mp3-scene/compare/v1.12.0...v1.12.1) (2026-11-16)

### Résumé

**Fiche release : pistes en « artiste - titre », avec leur genre.** Le tableau des pistes affiche l'artiste avant le
titre, gagne une colonne Genre (le tag de chaque piste), et ses colonnes N°, Durée, Débit et Genre sont centrées,
libellés compris. Sur téléphone, Débit et Genre restent masqués.

## [1.12.0](https://github.com/djkix/mp3-scene/compare/v1.11.0...v1.12.0) (2026-11-16)

### Résumé

**Nouvelle page Groupes.** Elle liste les groupes de release avec, pour chacun, le nombre de releases et le poids
total ; la liste se trie par colonne, se filtre par nom, par genre et par année, et affiche le total en bas. Un clic
sur un groupe ouvre ses releases, avec les filtres habituels (localisation, genre, année) et le total du groupe en
tête. Les groupes viennent du nom des releases : aucune migration, aucun scan.

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
