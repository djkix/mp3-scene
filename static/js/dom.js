// Aides DOM : tout est construit avec textContent / createElement (les noms viennent des fichiers, donc non fiables).
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k in node && k !== 'list') node[k] = v;
    else node.setAttribute(k, v === true ? '' : v);
  }
  node.append(...children.flat().filter((c) => c != null && c !== false));
  return node;
}

// Chemin de dossier -> segment de hash ('Singles/A' -> 'Singles/A' avec chaque partie encodée)
export const encodePath = (p) => p.split('/').map(encodeURIComponent).join('/');

// Nom de release tel qu'affiché : les espaces deviennent des « _ », comme dans les noms de la scène. L'adresse et la
// recherche gardent le vrai nom.
// nom d'une release à l'écran : soulignés à la place des espaces, première lettre en capitale (« pete_tong_-_… » -> « Pete_tong_-_… »)
export const relName = (name) => { const s = String(name ?? '').replace(/ /g, '_'); return s.charAt(0).toLocaleUpperCase() + s.slice(1); };

// Adresse de la fiche d'une release : son nom, lisible, et son identifiant, qui seul la désigne sans erreur
// (deux releases peuvent porter le même nom, et un nom tout en chiffres serait pris pour un identifiant).
export const relHref = (name, id) => `#/release/${encodeURIComponent(name)}${id ? `?id=${id}` : ''}`;

// Vignette sans pochette : la même pochette par défaut que le lecteur (masquée si elle-même manque)
export const NO_COVER = '/icons/cover-default.svg';
export const noCover = (e) => { if (e.target.src.endsWith(NO_COVER)) e.target.style.visibility = 'hidden'; else e.target.src = NO_COVER; };
