#!/usr/bin/env python3
"""
lotosystem.py - sistema estilo "tabela de movimentacao + ciclo + fechamentos"
(engenharia reversa dos 6 videos). Dependencias: python3 + numpy.

Comandos:
  python lotosystem.py atualizar                 # baixa resultados da Caixa
  python lotosystem.py status                    # tabela, ciclo, ranking
  python lotosystem.py gerar --modo fc84         # fc84 | fc79 | fc35 | fc17 | livre
  python lotosystem.py conferir --arquivo jogos_fc84.csv --concurso 3821
  python lotosystem.py backtest --modo fc84 --inicio 500

AVISO: nenhum sorteio depende do historico. O backtest existe para medir isso.
"""
import argparse, csv, itertools, json, math, os, random, sys, time, urllib.request
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "historico.csv")
API = "https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil/{}"

PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23}
FIB = {1, 2, 3, 5, 8, 13, 21}
MOLDURA = {1, 2, 3, 4, 5, 6, 10, 11, 15, 16, 20, 21, 22, 23, 24, 25}
MULT3 = {3, 6, 9, 12, 15, 18, 21, 24}
row = lambda d: (d - 1) // 5
col = lambda d: (d - 1) % 5

# premios fixos aproximados (R$) - AJUSTE conforme a Caixa; 14 e 15 sao variaveis (estimativa)
PREMIO = {11: 7.0, 12: 14.0, 13: 35.0, 14: 1500.0, 15: 1_000_000.0}
CUSTO_JOGO = 3.50  # AJUSTE para o valor vigente da aposta

# matriz FC35-equivalente: cada trio = 3 das 15 "variaveis" que ficam FORA do jogo.
# Verificada por forca bruta: acertando 3 fixas + 12 variaveis => >= 14 pontos.
FC35_OMIT = [(0,1,7),(0,3,5),(0,4,12),(1,3,4),(1,5,12),(2,5,11),(2,6,8),(2,9,13),(2,10,14),
             (3,7,12),(4,5,7),(6,9,10),(6,11,13),(6,13,14),(8,9,14),(8,10,11),(8,10,13),(9,11,14)]

# pesos do score (ajustaveis; teste via backtest em janelas separadas)
W = dict(f10=1.0, f20=0.5, seq=0.15, seq_len=0.02, seq_pen=0.05, falha=0.10, falha_len=0.02,
         alt=0.15, trans=0.15, retomada=0.05, ciclo_forte=0.25, ciclo_fraco=0.10)


# ----------------------------------------------------------------- dados
def load_hist(path=HIST):
    out = []
    if os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            out.append((int(r["concurso"]), r["data"], sorted(int(r[f"d{i}"]) for i in range(1, 16))))
    return sorted(out)


def save_hist(h, path=HIST):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["concurso", "data"] + [f"d{i}" for i in range(1, 16)])
        for c, d, n in sorted(h):
            w.writerow([c, d] + n)


def fetch(n=None, tries=4):
    url = API.format("" if n is None else n)
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            j = json.load(urllib.request.urlopen(req, timeout=20))
            return int(j["numero"]), j["dataApuracao"], sorted(int(x) for x in j["listaDezenas"])
        except Exception as e:
            err = e
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"falha ao buscar {url}: {err}")


def atualizar(desde=None):
    h = {c: (c, d, n) for c, d, n in load_hist()}
    ultimo = fetch()
    h[ultimo[0]] = ultimo
    ini = desde or 1
    faltam = [c for c in range(ini, ultimo[0] + 1) if c not in h]
    print(f"ultimo concurso na Caixa: {ultimo[0]} | faltam {len(faltam)}")
    for i, c in enumerate(faltam, 1):
        h[c] = fetch(c)
        if i % 100 == 0:
            save_hist(list(h.values())); print(f"  {i}/{len(faltam)}")
        time.sleep(0.12)
    save_hist(list(h.values()))
    print("historico salvo em", HIST)


def matriz(h):
    M = np.zeros((len(h), 25), dtype=np.int8)
    for i, (_, _, n) in enumerate(h):
        M[i, [x - 1 for x in n]] = 1
    return M


# ----------------------------------------------------------------- ciclo
def ciclos(h, cycle_from=None):
    """Retorna (faltantes_antes[t], pos_antes[t], lista_ciclos_fechados, faltantes_atuais, pos_atual).
    faltantes_antes[t] = dezenas que ainda nao sairam no ciclo ANTES do concurso t."""
    seen, pos, closed, miss_before, pos_before = set(), 0, [], [], []
    for c, _, n in h:
        if cycle_from and c < cycle_from:
            miss_before.append(set()); pos_before.append(0); continue
        miss_before.append(set(range(1, 26)) - seen); pos_before.append(pos)
        seen |= set(n); pos += 1
        if len(seen) == 25:
            closed.append((c, pos)); seen, pos = set(), 0
    return miss_before, pos_before, closed, set(range(1, 26)) - seen, pos


# ----------------------------------------------------------------- comportamento
def runs(seq):
    """seq: lista 0/1 (antigo->novo). retorna (valor_atual, comprimento_atual, comprimento_anterior)."""
    cur = seq[-1]; n = 0
    for v in reversed(seq):
        if v == cur: n += 1
        else: break
    prev = 0
    for v in reversed(seq[:len(seq) - n]):
        if v != cur: prev += 1
        else: break
    return cur, n, prev


def classificar(seq):
    cur, n, prev = runs(seq)
    s_in = n if cur == 1 else 0
    s_out = n if cur == 0 else 0
    last6 = seq[-6:]
    if len(last6) == 6 and all(last6[i] != last6[i + 1] for i in range(5)):
        return "alternancia", s_in, s_out
    if s_in >= 3: return "sequencia", s_in, s_out
    if s_out >= 3: return "falha", s_in, s_out
    if cur == 0 and prev >= 3: return "transicao", s_in, s_out      # saiu de uma sequencia
    if cur == 1 and prev >= 3: return "retomada", s_in, s_out       # voltou depois de falha longa
    return "irregular", s_in, s_out


def scores(M, faltantes, w=W):
    """Score por dezena usando SOMENTE M (historico ate agora)."""
    f10, f20 = M[-10:].mean(0), M[-20:].mean(0)
    out, info = np.zeros(25), []
    for d in range(25):
        seq = M[-24:, d].tolist()
        est, s_in, s_out = classificar(seq)
        s = w["f10"] * f10[d] + w["f20"] * f20[d]
        if est == "sequencia":
            s += w["seq"] + w["seq_len"] * min(s_in, 7) - w["seq_pen"] * max(0, s_in - 8)
        elif est == "falha":
            s -= w["falha"] + w["falha_len"] * s_out
        elif est == "alternancia":
            s += w["alt"] if seq[-1] == 0 else -w["alt"] * 0.7
        elif est == "transicao":
            s -= w["trans"]
        elif est == "retomada":
            s += w["retomada"]
        if (d + 1) in faltantes:
            s += w["ciclo_forte"] if len(faltantes) <= 4 else w["ciclo_fraco"]
        out[d] = s
        info.append((d + 1, est, s_in, s_out))
    return out, info


# ----------------------------------------------------------------- montagem
def ordenar(sc, excluir=(), fixas_forcadas=()):
    ordem = sorted((d for d in range(1, 26) if d not in excluir), key=lambda d: -sc[d - 1])
    for f in reversed(fixas_forcadas):
        if f in ordem: ordem.remove(f)
        ordem.insert(0, f)
    return ordem


def montar_grupos(restantes, n_grupos, tam):
    """G1 recebe as melhores; dentro do grupo tenta linhas diferentes do volante."""
    pool, grupos = list(restantes[: n_grupos * tam]), []
    for _ in range(n_grupos):
        g, linhas = [], set()
        for d in list(pool):
            if len(g) == tam: break
            if row(d) not in linhas:
                g.append(d); linhas.add(row(d)); pool.remove(d)
        for d in list(pool):
            if len(g) == tam: break
            g.append(d); pool.remove(d)
        grupos.append(sorted(g))
    return grupos


def posicional(ordem, n_fix, tam):
    """FC79: n_fix=6, tam=3 (18 dezenas). FC84: n_fix=3, tam=4 (19 dezenas). 4 jogos."""
    assert n_fix + 3 * tam == 15
    fixas = sorted(ordem[:n_fix])
    grupos = montar_grupos(ordem[n_fix:], 4, tam)
    jogos = [sorted(fixas + [d for k, g in enumerate(grupos) if k != om for d in g]) for om in range(4)]
    return jogos, dict(fixas=fixas, grupos=grupos)


def fc35(ordem):
    base = ordem[:18]; fixas = sorted(base[:3]); var = base[3:]
    jogos = [sorted(set(base) - {var[i] for i in om}) for om in FC35_OMIT]
    return jogos, dict(fixas=fixas, variaveis=sorted(var))


def fc17(ordem):
    base = ordem[:17]
    fracas = base[1:]  # as 16 mais fracas formam 8 pares omitidos; a melhor entra em todos
    pares = [(fracas[i], fracas[15 - i]) for i in range(8)]
    return [sorted(set(base) - set(p)) for p in pares], dict(dezenas=sorted(base))


def stats_jogo(j, ant):
    return dict(impares=sum(d % 2 for d in j), primos=sum(d in PRIMES for d in j), moldura=sum(d in MOLDURA for d in j),
                soma=sum(j), repetidas=len(set(j) & set(ant)) if ant else None,
                linhas_cheias=sum(sum(1 for d in j if row(d) == r) == 5 for r in range(5)),
                colunas_cheias=sum(sum(1 for d in j if col(d) == c) == 5 for c in range(5)),
                linhas_vazias=sum(all(row(d) != r for d in j) for r in range(5)))


def aprender_filtros(h):
    """Faixas (percentil 5-95) observadas no historico; com pouco historico usa padroes dos videos."""
    if len(h) < 200:
        return dict(impares=(7, 9), primos=(4, 7), moldura=(9, 11), soma=(170, 220), repetidas=(8, 10))
    S = [stats_jogo(n, h[i - 1][2] if i else None) for i, (_, _, n) in enumerate(h)]
    out = {}
    for k in ("impares", "primos", "moldura", "soma", "repetidas"):
        v = [s[k] for s in S if s[k] is not None]
        out[k] = (int(np.percentile(v, 5)), int(np.percentile(v, 95)))
    return out


def passa(j, ant, filt, dura=True):
    s = stats_jogo(j, ant)
    for k, (a, b) in filt.items():
        if s[k] is None: continue
        if not a <= s[k] <= b: return False
    return not dura or (s["linhas_cheias"] == 0 and s["colunas_cheias"] == 0 and s["linhas_vazias"] == 0)


def livre(ordem, sc, n, fixas, excluir, ant, filt, pool=21, seed=None):
    rnd = random.Random(seed)
    cand = [d for d in ordem if d not in excluir][:pool]
    for f in fixas:
        if f not in cand: cand.append(f)
    livres = [d for d in cand if d not in fixas]
    pesos = np.exp(np.array([sc[d - 1] for d in livres]) * 2)
    jogos, vistos, tent = [], set(), 0
    while len(jogos) < n and tent < 200000:
        tent += 1
        escolha = set()
        pl = list(zip(livres, pesos))
        while len(escolha) < 15 - len(fixas):
            tot = sum(p for d, p in pl if d not in escolha); r = rnd.random() * tot
            for d, p in pl:
                if d in escolha: continue
                r -= p
                if r <= 0: escolha.add(d); break
        j = tuple(sorted(escolha | set(fixas)))
        if j in vistos or not passa(j, ant, filt): continue
        vistos.add(j); jogos.append(list(j))
    return jogos


def construir(modo, h, M, faltantes, args=None, n=10):
    sc, info = scores(M, faltantes)
    excluir = set(getattr(args, "excluir", None) or [])
    fx = list(getattr(args, "fixas", None) or [])
    ordem = ordenar(sc, excluir, fx)
    ant = h[-1][2]
    if modo == "fc84": return (*posicional(ordem, 3, 4), sc, info)
    if modo == "fc79": return (*posicional(ordem, 6, 3), sc, info)
    if modo == "fc35": return (*fc35(ordem), sc, info)
    if modo == "fc17": return (*fc17(ordem), sc, info)
    filt = aprender_filtros(h)
    return livre(ordem, sc, n, fx, excluir, ant, filt, seed=getattr(args, "seed", None)), dict(filtros=filt, fixas=fx), sc, info


# ----------------------------------------------------------------- conferencia
def acertos(jogos, resultado):
    r = set(resultado)
    return [len(r & set(j)) for j in jogos]


def retorno(hits, custo=CUSTO_JOGO):
    return sum(PREMIO.get(k, 0) for k in hits) - custo * len(hits)


# ----------------------------------------------------------------- backtest
def backtest(modo, h, inicio, cycle_from=None, n=10, w=None):
    M = matriz(h)
    miss_b, pos_b, _, _, _ = ciclos(h, cycle_from)
    por_concurso, taxa, total_hits, ret = [], {k: 0 for k in range(11, 16)}, 0, 0.0
    njogos = 0
    for t in range(max(inicio, 30), len(h)):
        hh = h[:t]
        jogos, *_ = construir(modo, hh, M[:t], miss_b[t], None, n)
        hits = acertos(jogos, h[t][2])
        por_concurso.append(np.mean(hits)); total_hits += sum(hits); njogos += len(jogos)
        for k in taxa: taxa[k] += sum(1 for x in hits if x >= k)
        ret += retorno(hits)
    pc = np.array(por_concurso)
    # esperado ao acaso (hipergeometrica exata): media 9.0, dp por jogo 1.2247
    tot = math.comb(25, 15)
    esp_taxa = {k: sum(math.comb(15, x) * math.comb(10, 15 - x) for x in range(k, 16)) / tot for k in taxa}
    esp_ret = njogos * (sum(PREMIO.get(x, 0) * math.comb(15, x) * math.comb(10, 15 - x) / tot for x in range(11, 16)) - CUSTO_JOGO)
    z = (pc.mean() - 9.0) / (pc.std(ddof=1) / math.sqrt(len(pc))) if len(pc) > 2 else float("nan")
    return dict(concursos=len(pc), jogos=njogos, media_acertos=pc.mean(), esperado_acaso=9.0, z=z,
                taxa={k: taxa[k] / njogos for k in taxa}, taxa_acaso=esp_taxa, retorno=ret, retorno_acaso=esp_ret)


# ----------------------------------------------------------------- CLI
def cmd_status(a):
    h = load_hist(); M = matriz(h)
    cf = a.ciclo_desde
    if h[0][0] != 1 and not cf:
        cf = h[-4][0] if len(h) >= 4 else h[0][0]
        print(f"[aviso] historico nao comeca no concurso 1: ciclo contado a partir do {cf}. "
              f"Rode 'atualizar' para o ciclo correto, ou use --ciclo-desde.")
    mb, pb, closed, falt, pos = ciclos(h, cf)
    print(f"\nUltimo concurso: {h[-1][0]} ({h[-1][1]}): {' '.join(f'{x:02d}' for x in h[-1][2])}")
    if closed: print(f"Ultimo ciclo fechou no {closed[-1][0]} com {closed[-1][1]} concursos")
    print(f"Ciclo atual: {pos} concurso(s) | faltam sair: {sorted(falt) if falt else '(inicio de novo ciclo)'}")
    sc, info = scores(M, falt)
    print("\nTabela de movimentacao (ultimos 10; # saiu, . falhou):")
    print("dz  " + " ".join(f"{c % 100:02d}" for c, _, _ in h[-10:]) + "   f10  f20  estado")
    for d in range(25):
        lin = " ".join(" #" if M[-10:, d][i] else " ." for i in range(len(M[-10:])))
        print(f"{d+1:02d} {lin}   {M[-10:,d].mean():.1f}  {M[-20:,d].mean():.2f}  {info[d][1]} ({info[d][2]}/{info[d][3]})")
    print("\nRanking:", " ".join(f"{d:02d}" for d in ordenar(sc)))


def cmd_gerar(a):
    h = load_hist(); M = matriz(h)
    cf = a.ciclo_desde or (h[-4][0] if h[0][0] != 1 else None)
    _, _, _, falt, pos = ciclos(h, cf)
    jogos, meta, sc, info = construir(a.modo, h, M, falt, a, a.n)
    print(f"\nModo {a.modo} | base: ate o concurso {h[-1][0]} | ciclo atual: {pos} concursos, faltam {sorted(falt)}")
    print("Estrutura:", json.dumps(meta, ensure_ascii=False))
    ant = h[-1][2]
    for i, j in enumerate(jogos, 1):
        s = stats_jogo(j, ant)
        print(f"J{i:02d}: {' '.join(f'{d:02d}' for d in j)} | imp {s['impares']} rep {s['repetidas']} mold {s['moldura']} soma {s['soma']}")
    print(f"\nCusto: {len(jogos)} x R$ {CUSTO_JOGO:.2f} = R$ {len(jogos)*CUSTO_JOGO:.2f}")
    nome = os.path.join(HERE, f"jogos_{a.modo}.csv")
    with open(nome, "w", newline="") as f:
        w = csv.writer(f)
        for j in jogos: w.writerow(j)
    print("salvo em", nome)


def cmd_conferir(a):
    h = {c: n for c, _, n in load_hist()}
    if a.concurso not in h:
        sys.exit(f"concurso {a.concurso} nao esta no historico (rode 'atualizar')")
    jogos = [[int(x) for x in r] for r in csv.reader(open(a.arquivo)) if r]
    hits = acertos(jogos, h[a.concurso])
    for i, k in enumerate(hits, 1): print(f"J{i:02d}: {k} pontos")
    print(f"melhor: {max(hits)} | premiados (11+): {sum(k>=11 for k in hits)} | saldo estimado: R$ {retorno(hits):.2f}")


def cmd_backtest(a):
    h = load_hist()
    if len(h) < 300: sys.exit("historico curto demais para backtest: rode 'atualizar' (baixa tudo).")
    r = backtest(a.modo, h, a.inicio, None, a.n)
    print(f"\nBACKTEST {a.modo} | {r['concursos']} concursos, {r['jogos']} jogos")
    print(f"media de acertos/jogo: {r['media_acertos']:.3f} (acaso: 9.000)  z = {r['z']:+.2f}  (|z|<2 => indistinguivel do acaso)")
    for k in range(11, 16):
        print(f"  >= {k} pts: {r['taxa'][k]*100:.4f}%   (acaso: {r['taxa_acaso'][k]*100:.4f}%)")
    print(f"retorno estimado: R$ {r['retorno']:,.0f}   (acaso: R$ {r['retorno_acaso']:,.0f})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("atualizar"); s.add_argument("--desde", type=int)
    s = sp.add_parser("status"); s.add_argument("--ciclo-desde", type=int)
    s = sp.add_parser("gerar"); s.add_argument("--modo", default="fc84", choices=["fc84", "fc79", "fc35", "fc17", "livre"])
    s.add_argument("--fixas", type=int, nargs="*"); s.add_argument("--excluir", type=int, nargs="*")
    s.add_argument("--n", type=int, default=10); s.add_argument("--seed", type=int); s.add_argument("--ciclo-desde", type=int)
    s = sp.add_parser("conferir"); s.add_argument("--arquivo", required=True); s.add_argument("--concurso", type=int, required=True)
    s = sp.add_parser("backtest"); s.add_argument("--modo", default="fc84", choices=["fc84", "fc79", "fc35", "fc17", "livre"])
    s.add_argument("--inicio", type=int, default=500); s.add_argument("--n", type=int, default=10)
    a = p.parse_args()
    if a.cmd == "atualizar": atualizar(a.desde)
    else: globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    main()
