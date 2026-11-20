import { api, ApiError } from '../api.js';
import { t, catLabel } from '../i18n.js';
import { el, encodePath } from '../dom.js';
import { releaseList, loadFilters } from './releases.js';
import { tabs } from './groups.js';

export function render(container, params) {
  const path = params.rest || '';
  let dead = false, disposeList = null;
  const crumbs = [el('a', { href: '#/folders' }, t('Catégories'))];
  let acc = '';
  for (const seg of path ? path.split('/') : []) {
    acc = acc ? acc + '/' + seg : seg;
    crumbs.push(' › ', el('a', { href: '#/folders/' + encodePath(acc) }, acc === seg ? catLabel(seg) : seg)); // premier niveau : la catégorie
  }
  const page = (offset, tri = '') => api(`/folders?path=${encodeURIComponent(path)}&offset=${offset}&limit=50${tri}`);
  // un dossier ne montre que les releases de sa catégorie rangées là ; ce lien les donne toutes, où qu'elles soient
  if (path && !path.includes('/')) crumbs.push(' · ', el('a', { href: '#/?category=' + encodeURIComponent(path) }, t('Toute la catégorie')));
  container.replaceChildren(tabs('folders'), el('nav', { class: 'crumbs', 'aria-label': t("Fil d'Ariane") }, ...crumbs),
    el('p', { class: 'status' }, t('Chargement…')));

  let first = null;
  page(0).then((data) => {
    if (dead) return;
    first = data;
    const subs = el('ul', { class: 'sub-list' }, data.folders.map((f) =>
      el('li', {}, el('a', { href: '#/folders/' + encodePath(f.path) }, '▸ ', path ? f.name : catLabel(f.name)))));
    // catégories sans dossier à elles (Albums) : à la racine, elles mènent à la liste filtrée
    if (!path) loadFilters().then((f) => {
      if (!dead) subs.append(...f.categories.filter((c) => !data.folders.some((d) => d.name === c)).map((c) =>
        el('li', {}, el('a', { href: '#/?category=' + encodeURIComponent(c) }, '▸ ', catLabel(c)))));
    }).catch(() => {});
    const list = el('div');
    container.lastChild.replaceWith(...(data.folders.length ? [subs] : []), list);
    disposeList = releaseList(list, async (offset, tri) => {
      const d = first || await page(offset, tri); // première page déjà reçue avec les sous-dossiers
      first = null;
      return d.releases;
    }, { empty: data.folders.length ? '' : t('Dossier vide.'), sort: ['name', 'asc'] });
  }).catch((err) => {
    if (dead) return;
    container.lastChild.textContent = err instanceof ApiError && err.status === 404
      ? t('Dossier introuvable.') : err.message;
  });
  return () => { dead = true; disposeList?.(); };
}
