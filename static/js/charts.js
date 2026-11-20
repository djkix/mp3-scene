// Graphiques dessinés en SVG, sans bibliothèque : anneau (parts d'un tout), courbe (évolution), colonnes (par période).
// Le SVG ne contient que des nombres calculés ici ; les libellés passent par el() (texte), jamais par innerHTML.
import { el } from './dom.js';

const COLORS = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)'];
const svg = (label, body, viewBox) => {
  const box = el('div', { class: 'chart', role: 'img', 'aria-label': label });
  box.innerHTML = `<svg viewBox="${viewBox}" preserveAspectRatio="none">${body}</svg>`;
  return box;
};

// Les `max` plus grandes parts, le reste réuni sous `other` : [{name, n}], triées.
export function shares(rows, max = 5, other = 'Autres') {
  const sorted = rows.filter((r) => r.n > 0).sort((a, b) => b.n - a.n);
  const rest = sorted.slice(max).reduce((n, r) => n + r.n, 0);
  return [...sorted.slice(0, max), ...(rest ? [{ name: other, n: rest }] : [])];
}

// Anneau et sa légende (nom, pourcentage). `rows` : [{name, n}], six au plus (voir shares).
export function donut(label, rows) {
  const total = rows.reduce((n, r) => n + r.n, 0) || 1, C = 2 * Math.PI * 30;
  let at = 0;
  const arcs = rows.map((r, i) => {
    const len = (r.n / total) * C, arc = `<circle cx="40" cy="40" r="30" fill="none" stroke-width="14" style="stroke:${COLORS[i % 6]}"`
      + ` stroke-dasharray="${len.toFixed(2)} ${C.toFixed(2)}" stroke-dashoffset="${(-at).toFixed(2)}"/>`;
    at += len;
    return arc;
  }).join('');
  const ring = svg(label, `<g transform="rotate(-90 40 40)">${arcs}</g>`, '0 0 80 80');
  ring.classList.add('donut');
  // la légende porte le chiffre exact et le pourcentage ; `detail` (poids…) s'ajoute si la ligne en a un
  return el('div', { class: 'donut-box' }, ring, el('ul', { class: 'legend' }, rows.map((r, i) => el('li', {},
    el('i', { style: `background:${COLORS[i % 6]}` }), el('span', {}, r.name),
    el('b', {}, `${Number(r.n).toLocaleString()}${r.detail ? ` · ${r.detail}` : ''} · ${Math.round(100 * r.n / total)} %`)))));
}

// Sous une courbe ou des colonnes : la valeur du point survolé ou touché (`texts[i]`), la dernière au repos.
function readout(box, texts) {
  if (!texts?.length) return box;
  const out = el('p', { class: 'chart-val' }, texts.at(-1));
  const pick = (e) => {
    const r = box.getBoundingClientRect();
    out.textContent = texts[Math.min(texts.length - 1, Math.max(0, Math.floor((e.clientX - r.left) / r.width * texts.length)))];
  };
  box.addEventListener('pointermove', pick);
  box.addEventListener('pointerdown', pick);
  box.addEventListener('pointerleave', () => { out.textContent = texts.at(-1); });
  return el('div', {}, box, out);
}

// Courbe avec son aire : `values` dans l'ordre du temps ; `texts` : libellé exact de chaque point.
export function area(label, values, texts = null) {
  texts = texts && values.length >= 2 ? texts : null;
  if (values.length < 2) values = [0, ...values, 0].slice(0, Math.max(2, values.length + 1));
  const max = Math.max(1, ...values), w = 300, h = 80;
  const pts = values.map((v, i) => `${(i * w / (values.length - 1)).toFixed(1)},${(h - 4 - (v / max) * (h - 10)).toFixed(1)}`);
  return readout(svg(label, `<polygon points="0,${h} ${pts.join(' ')} ${w},${h}" style="fill:var(--tint)"/>`
    + `<polyline points="${pts.join(' ')}" fill="none" stroke-width="2" vector-effect="non-scaling-stroke" style="stroke:var(--c1)"/>`, `0 0 ${w} ${h}`), texts);
}

// Colonnes : une par période, dans l'ordre donné ; `texts` : libellé exact de chaque colonne.
export function columns(label, values, color = 0, texts = null) {
  const max = Math.max(1, ...values), w = 300, h = 60, step = w / Math.max(1, values.length);
  return readout(svg(label, values.map((v, i) => {
    const bh = Math.max(v ? 1 : 0, (v / max) * (h - 2));
    const bw = Math.min(step * 0.76, 22); // peu de périodes : des colonnes, pas des pavés
    return `<rect x="${(i * step + (step - bw) / 2).toFixed(1)}" y="${(h - bh).toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" style="fill:${COLORS[color]}"/>`;
  }).join(''), `0 0 ${w} ${h}`), texts);
}
