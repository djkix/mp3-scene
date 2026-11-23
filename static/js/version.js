import { api } from './api.js';

const REPO = 'djkix/mp3-scene';

// '1.2.0' est-elle plus récente que '1.1.3' ? Une version non numérotée ('dev') n'est jamais dépassée.
export function isNewer(latest, current) {
  const a = latest.split('.').map(Number), b = current.split('.').map(Number);
  if ([...a, ...b].some(Number.isNaN)) return false;
  for (let i = 0; i < 3; i++) if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
  return false;
}

// ponytail: une seule vérification par chargement de page ; ajouter une relance périodique si l'appli reste ouverte des jours.
let cached;
export const versionInfo = () => (cached ??= load().catch((err) => { cached = undefined; throw err; }));

async function load() {
  const { version } = await api('/admin/version');
  let latest = null, url = null;
  try { // GitHub injoignable ou quota dépassé : la version installée s'affiche quand même
    const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`);
    if (res.ok) {
      const rel = await res.json();
      latest = String(rel.tag_name).replace(/^v/, '');
      // seul un lien vers les publications de ce dépôt est affiché
      url = typeof rel.html_url === 'string' && rel.html_url.startsWith(`https://github.com/${REPO}/`) ? rel.html_url : null;
    }
  } catch { /* hors ligne */ }
  return { version, latest, url, update: latest !== null && isNewer(latest, version) };
}
