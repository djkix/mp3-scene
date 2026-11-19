import { fmtDuration, fmtSize } from '../api.js';
import { t, catLabel } from '../i18n.js';

const enc = encodeURIComponent;

// Lignes <dt>/<dd> de la fiche ; les champs null sont omis. Artiste, année, groupe et genre mènent à la liste
// correspondante. `el` est injecté pour pouvoir tester sans navigateur.
export function infoRows(rel, el) {
  return [[t('Artiste'), rel.artist, (v) => `#/artists/${enc(v)}`], [t('Titre'), rel.title], [t('Source'), rel.source, (v) => `#/?source=${enc(v)}`],
    [t('Année'), rel.year, (v) => `#/?year=${enc(v)}`], [t('Groupe'), rel.grp, (v) => `#/groups/${enc(v)}`],
    [t('Catégorie'), rel.category && catLabel(rel.category)], [t('Genre'), rel.genre, (v) => `#/?genre=${enc(v)}`],
    [t('Taille'), rel.size == null ? null : fmtSize(rel.size)],
    [t('Durée'), rel.duration == null ? null : fmtDuration(rel.duration)]]
    .filter(([, v]) => v != null && v !== '')
    // à plat : el() n'aplatit qu'un niveau
    .flatMap(([k, v, href]) => [el('dt', {}, k), el('dd', {}, href ? el('a', { href: href(v) }, String(v)) : String(v))]);
}
