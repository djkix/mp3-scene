import { fmtDate, fmtDuration, fmtSize } from '../api.js';
import { t, catLabel } from '../i18n.js';

const enc = encodeURIComponent;

// Lignes <dt>/<dd> de la fiche ; les champs null sont omis. Artiste, année, groupe et genre mènent à la liste
// correspondante ; le catalogue mène au label. `el` est injecté pour pouvoir tester sans navigateur.
// Pastille de chaque valeur, colorée par type : `src` provenance (source, groupe), `cls` classement (artiste, année,
// catégorie, genre), `ed` édition (label, catalogue), `num` mesures (date, taille, durée). Le titre reste en texte.
// Une pastille sans lien est grise : seules les vertes se cliquent.
export function infoRows(rel, el) {
  return [[t('Artiste'), rel.artist, (v) => `#/artists/${enc(v)}`, 'cls'], [t('Titre'), rel.title],
    [t('Source'), rel.source, (v) => `#/?source=${enc(v)}`, 'src'], [t('Année'), rel.year, (v) => `#/?year=${enc(v)}`, 'cls'],
    [t('Date'), rel.date == null ? null : fmtDate(rel.date), null, 'num'], [t('Groupe'), rel.grp, (v) => `#/groups/${enc(v)}`, 'src'],
    [t('Label'), rel.label, (v) => `#/labels/${enc(v)}`, 'ed'],
    [t('Catalogue'), rel.catalog, rel.label ? () => `#/labels/${enc(rel.label)}` : null, 'ed'],
    [t('Catégorie'), rel.category && catLabel(rel.category), () => `#/?category=${enc(rel.category)}`, 'cls'],
    // série : ajoutée une fois ses volumes connus (deux au moins), elle mène à la page de la série
    [t('Série'), rel.series_name, (v) => `#/series/${enc(v)}`, 'cls'],
    [t('Genre'), rel.genre, (v) => `#/?genre=${enc(v)}`, 'cls'],
    [t('Taille'), rel.size == null ? null : fmtSize(rel.size), null, 'num'],
    [t('Durée'), rel.duration == null ? null : fmtDuration(rel.duration), null, 'num'],
    [t('Format'), rel.format, null, 'num'],
    [t('Débit'), rel.bitrate ? `${Math.round(rel.bitrate / 1000)} kbit/s` : null, null, 'num'],
    [t('Écoutes'), rel.plays || null, null, 'num'],
    [t('Fréquence'), rel.sample_rate ? `${(rel.sample_rate / 1000).toLocaleString()} kHz` : null, null, 'num']]
    .filter(([, v]) => v != null && v !== '')
    // à plat : el() n'aplatit qu'un niveau
    .flatMap(([k, v, href, kind]) => [el('dt', {}, k), el('dd', {},
      !kind ? String(v) : el(href ? 'a' : 'span', { class: `pill pill-${kind}`, href: href ? href(v) : null }, String(v)))]);
}
