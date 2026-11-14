import { fmtDuration, fmtSize } from '../api.js';
import { t } from '../i18n.js';

// Lignes <dt>/<dd> de la fiche ; les champs null sont omis. `el` est injecté pour pouvoir tester sans navigateur.
export function infoRows(rel, el) {
  return [[t('Artiste'), rel.artist], [t('Titre'), rel.title], [t('Source'), rel.source], [t('Année'), rel.year],
    [t('Groupe'), rel.grp], [t('Catégorie'), rel.category], [t('Genre'), rel.genre],
    [t('Taille'), rel.size == null ? null : fmtSize(rel.size)],
    [t('Durée'), rel.duration == null ? null : fmtDuration(rel.duration)]]
    .filter(([, v]) => v != null && v !== '')
    .flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v))]); // à plat : el() n'aplatit qu'un niveau
}
