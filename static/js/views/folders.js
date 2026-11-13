import { api, ApiError } from '../api.js';
import { el, encodePath } from '../dom.js';
import { releaseList } from './releases.js';

export function render(container, params) {
  const path = params.rest || '';
  let dead = false, disposeList = null;
  const crumbs = [el('a', { href: '#/folders' }, 'Dossiers')];
  let acc = '';
  for (const seg of path ? path.split('/') : []) {
    acc = acc ? acc + '/' + seg : seg;
    crumbs.push(' › ', el('a', { href: '#/folders/' + encodePath(acc) }, seg));
  }
  const page = (offset) => api(`/folders?path=${encodeURIComponent(path)}&offset=${offset}&limit=50`);
  container.replaceChildren(el('nav', { class: 'crumbs', 'aria-label': "Fil d'Ariane" }, ...crumbs),
    el('p', { class: 'status' }, 'Chargement…'));

  let first = null;
  page(0).then((data) => {
    if (dead) return;
    first = data;
    const subs = el('ul', { class: 'sub-list' }, data.folders.map((f) =>
      el('li', {}, el('a', { href: '#/folders/' + encodePath(f.path) }, '▸ ', f.name))));
    const list = el('div');
    container.lastChild.replaceWith(...(data.folders.length ? [subs] : []), list);
    disposeList = releaseList(list, async (offset) => (offset === 0 ? first : await page(offset)).releases,
      { empty: data.folders.length ? '' : 'Dossier vide.' });
  }).catch((err) => {
    if (dead) return;
    container.lastChild.textContent = err instanceof ApiError && err.status === 404
      ? 'Dossier introuvable.' : err.message;
  });
  return () => { dead = true; disposeList?.(); };
}
