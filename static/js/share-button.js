// Bouton « Partager » : demande au serveur un lien signé (7 jours) et le copie dans le presse-papiers.
import { api } from './api.js';
import { el } from './dom.js';
import { t as tr } from './i18n.js';
import { player } from './player.js';

export function shareButton(kind, id) {
  const btn = el('button', { type: 'button', 'data-ico': 'share', onclick: async () => {
    btn.disabled = true;
    try {
      const { url } = await api('/share', { method: 'POST', body: { kind, id } });
      try {
        await navigator.clipboard.writeText(url);
        player.flash(tr('Lien copié, valable 7 jours.'));
      } catch { prompt(tr('Lien de partage, valable 7 jours :'), url); } // presse-papiers refusé : on montre le lien
    } catch (err) { player.flash(err.message); }
    btn.disabled = false;
  } }, tr('Partager'));
  return btn;
}
