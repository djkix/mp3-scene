// Silences d'une piste, lus sur sa forme d'onde (volume moyen de 0 à 255, le plus fort de la piste valant 255).
// [[début, fin]] en secondes : en tête ou en queue à partir de `edge` secondes, au milieu à partir de `middle`
// (la piste cachée après trois minutes de vide). Une fin égale à `duration` : silence jusqu'au bout.
// ponytail: 800 crêtes par piste, donc ~9 s par crête sur un mix de 2 h ; assez pour les blancs, pas pour couper net
export function gaps(peaks, duration, { floor = 5, edge = 1.5, middle = 8 } = {}) {
  const n = peaks.length, out = [];
  if (!n || !(duration > 0)) return out;
  for (let i = 0; i < n;) {
    if (peaks[i] >= floor) { i++; continue; }
    let j = i;
    while (j < n && peaks[j] < floor) j++;
    const from = i * duration / n, to = j * duration / n;
    if (i > 0 || j < n) { // une piste entièrement muette : rien à sauter
      if (to - from >= (i === 0 || j === n ? edge : middle)) out.push([from, j === n ? duration : to]);
    }
    i = j;
  }
  return out;
}
