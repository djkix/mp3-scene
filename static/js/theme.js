// Thème choisi dans Compte : 'light', 'dark', ou '' pour suivre le système. Appliqué par l'attribut data-theme de <html>.
// ponytail: appliqué au chargement des modules, donc un bref passage par le thème du système est possible à l'ouverture.
export const theme = () => { try { return localStorage.getItem('theme') || ''; } catch { return ''; } };

export function setTheme(v) {
  try { if (v) localStorage.setItem('theme', v); else localStorage.removeItem('theme'); } catch { /* stockage indisponible */ }
  apply();
}

function apply() {
  const v = theme();
  if (v === 'light' || v === 'dark') document.documentElement.dataset.theme = v;
  else delete document.documentElement.dataset.theme;
}
apply();
