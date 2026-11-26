// Infobulle des pictos : au survol de la souris ou au focus clavier, le titre (attribut title) d'un bouton ou d'un lien
// qui n'affiche pas de texte s'affiche tout de suite au-dessus de lui, dans le style de l'application, au lieu de
// l'infobulle du navigateur (lente, et absente au clavier). Le titre passe dans data-tip pour ne pas s'afficher deux fois.
// ponytail: rien au toucher (pas de survol sur téléphone) ; le nom reste lu par les lecteurs d'écran (aria-label ou texte)
const tip = document.createElement('div');
tip.className = 'tip';
tip.setAttribute('role', 'tooltip');
tip.hidden = true;
let owner = null;

// un picto : bouton ou lien dont le texte visible est vide (taille 0, icône seule ou caractère seul)
const iconish = (n) => n.matches('button, a, [role="button"]')
  && (n.matches('.icon, .round, [data-ico], .rel-cover') || (n.textContent || '').trim().length <= 2 || getComputedStyle(n).fontSize === '0px');

function show(n) {
  if (n.title) { n.dataset.tip = n.title; n.removeAttribute('title'); } // un title remis par le code est repris
  if (!n.dataset.tip) return;
  owner = n;
  tip.textContent = n.dataset.tip;
  if (!tip.isConnected) document.body.append(tip);
  tip.hidden = false;
  const r = n.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
  const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
  const top = r.top - h - 8 < 8 ? r.bottom + 8 : r.top - h - 8; // sous le picto s'il n'y a pas la place au-dessus
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function hide() { owner = null; tip.hidden = true; }

const find = (e) => { const n = e.target.closest?.('[title], [data-tip]'); return n && iconish(n) ? n : null; };
document.addEventListener('pointerover', (e) => { if (e.pointerType !== 'mouse') return; const n = find(e); if (n) show(n); else if (owner && !owner.contains(e.target)) hide(); });
document.addEventListener('pointerout', (e) => { if (owner && !owner.contains(e.relatedTarget)) hide(); });
document.addEventListener('focusin', (e) => { const n = find(e); if (n && n.matches(':focus-visible')) show(n); });
document.addEventListener('focusout', hide);
for (const ev of ['scroll', 'pointerdown', 'hashchange']) addEventListener(ev, hide, true);
