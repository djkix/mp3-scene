import { EN } from './en.js';

// Traduction minimale : le français sert de clé (voir en.js). Langue fixée au chargement ; setLang recharge la page.
const pick = () => {
  try {
    const s = typeof localStorage === 'undefined' ? null : localStorage.getItem('lang');
    if (s === 'fr' || s === 'en') return s;
  } catch { /* stockage indisponible */ }
  try {
    if (typeof window !== 'undefined' && typeof navigator !== 'undefined' && // sous Node (pas de window) : 'fr'
      !/^fr/i.test(navigator.language || 'fr')) return 'en';
  } catch { /* navigator indisponible */ }
  return 'fr';
};

export const lang = pick();
export const locale = lang === 'fr' ? 'fr-FR' : 'en-GB';

export function t(fr, ...args) {
  const s = lang === 'fr' ? fr : EN[fr] ?? fr;
  return s.replace(/\{(\d+)\}/g, (m, i) => (i < args.length ? args[i] : m));
}

// Libellé d'une catégorie (dossier racine) : « 02.Various Artists - Compilations » -> « Compilations ».
// « 03.Various Artists - Live And Radio » -> « Live & Radio ».
export const catLabel = (c) => String(c ?? '').replace(/^\d+\.\s*/, '').replace(/^Various Artists - /i, '')
  .replace(/^live and radio$/i, 'Live & Radio');

export function setLang(l) {
  try { localStorage.setItem('lang', l); } catch { /* idem */ }
  location.reload();
}
