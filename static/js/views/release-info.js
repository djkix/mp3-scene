import { fmtDuration, fmtSize } from '../api.js';

// Lignes <dt>/<dd> de la fiche ; les champs null sont omis. `el` est injecté pour pouvoir tester sans navigateur.
export function infoRows(rel, el) {
  return [['Artiste', rel.artist], ['Titre', rel.title], ['Source', rel.source], ['Année', rel.year],
    ['Groupe', rel.grp], ['Catégorie', rel.category], ['Genre', rel.genre],
    ['Taille', rel.size == null ? null : fmtSize(rel.size)],
    ['Durée', rel.duration == null ? null : fmtDuration(rel.duration)]]
    .filter(([, v]) => v != null && v !== '')
    .flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v))]); // à plat : el() n'aplatit qu'un niveau
}
