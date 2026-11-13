export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Utilisateur connecté ({username, role}) ou null ; partagé entre le routeur et les vues.
export const session = { user: null };

export async function api(path, { method = 'GET', body } = {}) {
  const headers = {};
  if (method !== 'GET') headers['X-CSRF'] = '1';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch('/api' + path, {
      method, headers, credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Serveur injoignable.');
  }
  if (res.status === 401 && path !== '/login') {
    session.user = null;
    location.hash = '#/login';
  }
  if (!res.ok) {
    let message = 'Erreur ' + res.status;
    try {
      const d = (await res.json()).detail;
      if (typeof d === 'string') message = d;
    } catch { /* corps non JSON */ }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? null : res.json();
}

export function fmtSize(bytes) {
  if (bytes == null) return '';
  const units = ['o', 'Ko', 'Mo', 'Go', 'To'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return (i === 0 ? String(bytes) : bytes.toFixed(bytes < 10 ? 1 : 0).replace('.', ',')) + ' ' + units[i];
}

export function fmtDate(ts) {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function fmtDuration(seconds) {
  const s = Math.round(seconds || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
