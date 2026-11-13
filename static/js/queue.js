// File de lecture — logique pure (ni DOM, ni stockage, ni réseau) : testée sous node.
// `order` est l'ordre de lecture (indices de `tracks`) : identité sans aléatoire, mélangé avec la courante en tête sinon.
const REPEATS = ['off', 'all', 'one'];

export class Queue {
  constructor({ random = Math.random } = {}) {
    this.random = random;
    this.tracks = [];
    this.index = -1;
    this.repeat = 'off';
    this._shuffle = false;
    this.order = [];
  }

  get shuffle() { return this._shuffle; }
  set shuffle(v) { this._shuffle = !!v; this._reorder(); }

  _mix(a) { // Fisher-Yates
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(this.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  _reorder() {
    const all = this.tracks.map((_, i) => i);
    this.order = !this._shuffle ? all
      : this.index < 0 ? this._mix(all) : [this.index, ...this._mix(all.filter((i) => i !== this.index))];
  }

  _pos() { return this.order.indexOf(this.index); }

  current() { return this.tracks[this.index] ?? null; }

  replace(tracks, startIndex = 0) {
    this.tracks = [...tracks];
    this.index = this.tracks.length ? Math.min(Math.max(startIndex | 0, 0), this.tracks.length - 1) : -1;
    this._reorder();
  }

  append(tracks) {
    const start = this.tracks.length;
    this.tracks.push(...tracks);
    if (this.index < 0) {
      if (this.tracks.length) this.index = 0;
      this._reorder();
    } else if (this._shuffle) { // les nouvelles pistes sont mélangées avec celles qui restent à jouer
      const p = this._pos();
      const added = this.tracks.slice(start).map((_, k) => start + k);
      this.order = [...this.order.slice(0, p + 1), ...this._mix([...this.order.slice(p + 1), ...added])];
    } else this._reorder();
  }

  remove(i) {
    if (!Number.isInteger(i) || i < 0 || i >= this.tracks.length) return;
    const p = this.order.indexOf(i);
    this.tracks.splice(i, 1);
    this.order.splice(p, 1);
    this.order = this.order.map((j) => (j > i ? j - 1 : j));
    if (!this.tracks.length) this.index = -1;
    else if (i === this.index) this.index = this.order[Math.min(p, this.order.length - 1)]; // la suivante, ou la nouvelle dernière
    else if (i < this.index) this.index--;
  }

  clear() { this.replace([]); }

  jump(i) {
    if (!Number.isInteger(i) || i < 0 || i >= this.tracks.length) return null;
    if (this._shuffle && i !== this.index) { // place la piste choisie juste après la courante : rien n'est perdu
      const o = this.order.filter((j) => j !== i);
      o.splice(o.indexOf(this.index) + 1, 0, i);
      this.order = o;
    }
    this.index = i;
    return this.current();
  }

  next({ auto = false } = {}) {
    if (this.index < 0) return null;
    if (auto && this.repeat === 'one') return this.current();
    const p = this._pos();
    if (p + 1 < this.order.length) this.index = this.order[p + 1];
    else if (this.repeat === 'all') this.index = this.order[0];
    else return null;
    return this.current();
  }

  prev() {
    if (this.index < 0) return null;
    const p = this._pos();
    if (p > 0) this.index = this.order[p - 1];
    else if (this.repeat === 'all') this.index = this.order[this.order.length - 1];
    else return null;
    return this.current();
  }

  toJSON() {
    return { tracks: this.tracks, index: this.index, shuffle: this._shuffle, repeat: this.repeat };
  }

  // Données lues du stockage local : jamais fiables, toute valeur invalide donne une file vide ou une valeur par défaut.
  static fromJSON(obj, opts) {
    const q = new Queue(opts);
    if (!obj || typeof obj !== 'object') return q;
    const tracks = Array.isArray(obj.tracks) ? obj.tracks.filter((t) => t && typeof t === 'object' && t.id != null) : [];
    const i = Number.isInteger(obj.index) && obj.index >= 0 && obj.index < tracks.length ? obj.index : 0;
    q.repeat = REPEATS.includes(obj.repeat) ? obj.repeat : 'off';
    q._shuffle = obj.shuffle === true;
    q.replace(tracks, i); // ponytail: l'ordre mélangé est re-tiré au rechargement (historique « précédent » perdu)
    return q;
  }
}
