// Lógica do sistema (porta do lotosystem.py). Sem DOM: roda no navegador e no Node.
const ALL = Array.from({length: 25}, (_, i) => i + 1);
const row = d => Math.floor((d - 1) / 5), col = d => (d - 1) % 5;
const PRIMOS = new Set([2,3,5,7,11,13,17,19,23]);
const MOLD = new Set([1,2,3,4,5,6,10,11,15,16,20,21,22,23,24,25]);
const FC35 = [[0,1,7],[0,3,5],[0,4,12],[1,3,4],[1,5,12],[2,5,11],[2,6,8],[2,9,13],[2,10,14],[3,7,12],[4,5,7],[6,9,10],[6,11,13],[6,13,14],[8,9,14],[8,10,11],[8,10,13],[9,11,14]];
const W = {f10:1, f20:.5, seq:.15, seqLen:.02, seqPen:.05, falha:.10, falhaLen:.02, alt:.15, trans:.15, retomada:.05, cicloF:.25, cicloW:.10};
const PREMIO = {11:7, 12:14, 13:35, 14:1500, 15:1000000};

const parseCSV = t => t.trim().split(/\r?\n/).slice(1).map(l => {
  const a = l.split(','); return {c: +a[0], d: a[1], n: a.slice(2, 17).map(Number).sort((x, y) => x - y)};
}).filter(r => r.n.length === 15 && r.n.every(Number.isFinite)).sort((a, b) => a.c - b.c);

const matriz = h => h.map(r => { const v = new Uint8Array(25); r.n.forEach(x => v[x - 1] = 1); return v; });

function ciclos(h, from) {
  let seen = new Set(), pos = 0; const closed = [], mb = [];
  for (const r of h) {
    if (from && r.c < from) { mb.push(new Set()); continue; }
    mb.push(new Set(ALL.filter(d => !seen.has(d))));
    r.n.forEach(x => seen.add(x)); pos++;
    if (seen.size === 25) { closed.push([r.c, pos]); seen = new Set(); pos = 0; }
  }
  return {mb, closed, falt: new Set(ALL.filter(d => !seen.has(d))), pos};
}

function runs(s) {
  const cur = s[s.length - 1]; let n = 0, p = 0;
  for (let i = s.length - 1; i >= 0 && s[i] === cur; i--) n++;
  for (let i = s.length - n - 1; i >= 0 && s[i] !== cur; i--) p++;
  return [cur, n, p];
}
function classificar(seq) {
  const [cur, n, prev] = runs(seq), sIn = cur ? n : 0, sOut = cur ? 0 : n, l6 = seq.slice(-6);
  if (l6.length === 6 && l6.every((v, i) => i === 5 || v !== l6[i + 1])) return ['alternancia', sIn, sOut];
  if (sIn >= 3) return ['sequencia', sIn, sOut];
  if (sOut >= 3) return ['falha', sIn, sOut];
  if (cur === 0 && prev >= 3) return ['transicao', sIn, sOut];
  if (cur === 1 && prev >= 3) return ['retomada', sIn, sOut];
  return ['irregular', sIn, sOut];
}
function scores(M, L, falt) {            // usa apenas M[0..L-1]
  const sc = [], info = [];
  for (let d = 0; d < 25; d++) {
    let a = 0, b = 0; const seq = [];
    for (let i = Math.max(0, L - 10); i < L; i++) a += M[i][d];
    for (let i = Math.max(0, L - 20); i < L; i++) b += M[i][d];
    for (let i = Math.max(0, L - 24); i < L; i++) seq.push(M[i][d]);
    const [est, si, so] = classificar(seq);
    let s = W.f10 * a / Math.min(10, L) + W.f20 * b / Math.min(20, L);
    if (est === 'sequencia') s += W.seq + W.seqLen * Math.min(si, 7) - W.seqPen * Math.max(0, si - 8);
    else if (est === 'falha') s -= W.falha + W.falhaLen * so;
    else if (est === 'alternancia') s += seq[seq.length - 1] === 0 ? W.alt : -W.alt * .7;
    else if (est === 'transicao') s -= W.trans;
    else if (est === 'retomada') s += W.retomada;
    if (falt.has(d + 1)) s += falt.size <= 4 ? W.cicloF : W.cicloW;
    sc.push(s); info.push({d: d + 1, est, sIn: si, sOut: so});
  }
  return {sc, info};
}

function ordenar(sc, excl = [], fix = []) {
  const o = ALL.filter(d => !excl.includes(d)).sort((a, b) => sc[b - 1] - sc[a - 1]);
  for (const f of [...fix].reverse()) { const i = o.indexOf(f); if (i >= 0) o.splice(i, 1); o.unshift(f); }
  return o;
}
function montarGrupos(rest, ng, tam) {
  const pool = rest.slice(0, ng * tam), gs = [];
  for (let k = 0; k < ng; k++) {
    const g = [], lin = new Set();
    for (const d of [...pool]) if (g.length < tam && !lin.has(row(d))) { g.push(d); lin.add(row(d)); pool.splice(pool.indexOf(d), 1); }
    for (const d of [...pool]) if (g.length < tam) { g.push(d); pool.splice(pool.indexOf(d), 1); }
    gs.push(g.sort((a, b) => a - b));
  }
  return gs;
}
const srt = a => [...a].sort((x, y) => x - y);
function posicional(o, nf, tam) {
  const fixas = srt(o.slice(0, nf)), grupos = montarGrupos(o.slice(nf), 4, tam);
  return {jogos: [0,1,2,3].map(om => srt([...fixas, ...grupos.flatMap((g, k) => k === om ? [] : g)])), meta: {fixas, grupos}};
}
function fc35(o) {
  const base = o.slice(0, 18), fixas = srt(base.slice(0, 3)), v = base.slice(3);
  return {jogos: FC35.map(om => srt(base.filter(d => !om.some(i => v[i] === d)))), meta: {fixas, variaveis: srt(v)}};
}
function fc17(o) {
  const base = o.slice(0, 17), f = base.slice(1);
  return {jogos: [0,1,2,3,4,5,6,7].map(i => srt(base.filter(d => d !== f[i] && d !== f[15 - i]))), meta: {dezenas: srt(base)}};
}

function statsJogo(j, ant) {
  const cnt = fn => j.filter(fn).length, cheia = (f, k) => cnt(d => f(d) === k) === 5;
  return {impares: cnt(d => d % 2), primos: cnt(d => PRIMOS.has(d)), moldura: cnt(d => MOLD.has(d)), soma: j.reduce((a, b) => a + b, 0),
    repetidas: ant ? cnt(d => ant.includes(d)) : null,
    lCheias: [0,1,2,3,4].filter(k => cheia(row, k)).length, cCheias: [0,1,2,3,4].filter(k => cheia(col, k)).length,
    lVazias: [0,1,2,3,4].filter(k => cnt(d => row(d) === k) === 0).length};
}
function pct(v, p) { v = srt(v); const x = (v.length - 1) * p / 100, i = Math.floor(x); return Math.floor(v[i] + (v[Math.min(i + 1, v.length - 1)] - v[i]) * (x - i)); }
function aprenderFiltros(h) {
  if (h.length < 200) return {impares: [7,9], primos: [4,7], moldura: [9,11], soma: [170,220], repetidas: [8,10]};
  const S = h.map((r, i) => statsJogo(r.n, i ? h[i - 1].n : null)), o = {};
  for (const k of ['impares','primos','moldura','soma','repetidas']) { const v = S.filter(s => s[k] !== null).map(s => s[k]); o[k] = [pct(v, 5), pct(v, 95)]; }
  return o;
}
function passa(j, ant, f) {
  const s = statsJogo(j, ant);
  for (const k in f) if (s[k] !== null && (s[k] < f[k][0] || s[k] > f[k][1])) return false;
  return !s.lCheias && !s.cCheias && !s.lVazias;
}
function livre(o, sc, n, fix, excl, ant, filt, pool = 21) {
  let cand = o.filter(d => !excl.includes(d)).slice(0, pool);
  fix.forEach(f => { if (!cand.includes(f)) cand.push(f); });
  const livres = cand.filter(d => !fix.includes(d)), pesos = livres.map(d => Math.exp(sc[d - 1] * 2));
  const jogos = [], vistos = new Set();
  for (let t = 0; jogos.length < n && t < 60000; t++) {
    const esc = new Set();
    while (esc.size < 15 - fix.length) {
      let tot = 0; livres.forEach((d, i) => { if (!esc.has(d)) tot += pesos[i]; });
      let r = Math.random() * tot;
      for (let i = 0; i < livres.length; i++) { if (esc.has(livres[i])) continue; r -= pesos[i]; if (r <= 0) { esc.add(livres[i]); break; } }
    }
    const j = srt([...esc, ...fix]), k = j.join(',');
    if (!vistos.has(k) && passa(j, ant, filt)) { vistos.add(k); jogos.push(j); }
  }
  return {jogos, meta: {filtros: filt, fixas: fix}};
}
function construir(modo, h, M, L, falt, o = {}) {
  const {sc, info} = scores(M, L, falt), ord = ordenar(sc, o.excl || [], o.fix || []);
  const r = modo === 'fc84' ? posicional(ord, 3, 4) : modo === 'fc79' ? posicional(ord, 6, 3) : modo === 'fc35' ? fc35(ord)
    : modo === 'fc17' ? fc17(ord) : livre(ord, sc, o.n || 10, o.fix || [], o.excl || [], h[L - 1].n, aprenderFiltros(h.slice(0, L)));
  return {...r, sc, info, ord};
}

const acertos = (jogos, res) => jogos.map(j => j.filter(d => res.includes(d)).length);
const comb = (n, k) => { let r = 1; for (let i = 1; i <= k; i++) r = r * (n - k + i) / i; return Math.round(r); };
const retorno = (hits, custo) => hits.reduce((a, k) => a + (PREMIO[k] || 0), 0) - custo * hits.length;

function backtest(modo, h, ini, custo, n = 10) {
  const M = matriz(h), {mb} = ciclos(h, null), tot = comb(25, 15); let nj = 0, ret = 0; const pc = [], taxa = {11:0,12:0,13:0,14:0,15:0};
  for (let t = Math.max(ini, 30); t < h.length; t++) {
    const {jogos} = construir(modo, h, M, t, mb[t], {n}), hits = acertos(jogos, h[t].n);
    pc.push(hits.reduce((a, b) => a + b, 0) / hits.length); nj += hits.length; ret += retorno(hits, custo);
    for (const k in taxa) taxa[k] += hits.filter(x => x >= +k).length;
  }
  const m = pc.reduce((a, b) => a + b, 0) / pc.length, sd = Math.sqrt(pc.reduce((a, b) => a + (b - m) ** 2, 0) / (pc.length - 1));
  const pk = k => { let s = 0; for (let x = k; x <= 15; x++) s += comb(15, x) * comb(10, 15 - x); return s / tot; };
  const esp = {}; for (const k in taxa) { taxa[k] /= nj; esp[k] = pk(+k); }
  let er = 0; for (let x = 11; x <= 15; x++) er += PREMIO[x] * comb(15, x) * comb(10, 15 - x) / tot;
  return {concursos: pc.length, jogos: nj, media: m, z: (m - 9) / (sd / Math.sqrt(pc.length)), taxa, esp, ret, retAcaso: nj * (er - custo)};
}
if (typeof module !== 'undefined') module.exports = {statsJogo, parseCSV, matriz, ciclos, scores, ordenar, construir, acertos, backtest, ALL};
