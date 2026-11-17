# 🎱 Lotofácil Lab

App estático (GitHub Pages) que reproduz o sistema dos vídeos: tabela de movimentação, ciclo das dezenas,
estados por dezena, fechamentos (FC79, FC84, FC35, 17→8), gerador livre com filtros, conferidor e **backtest** contra o acaso.

> Ferramenta de análise, não de previsão. Cada sorteio é independente do histórico.

## Publicar
1. Crie um repositório e envie todo o conteúdo desta pasta (incluindo `.github/`).
2. **Settings → Pages → Deploy from a branch → `main` / root.**
3. **Actions → "Atualizar resultados (Caixa)" → Run workflow** (a 1ª execução baixa todo o histórico, ~10 min).
   Depois roda sozinho todo dia às 23:30 (Brasília).

Só consulta a API oficial da Caixa (`servicebus2.caixa.gov.br`). Se a Caixa bloquear os servidores do GitHub,
o workflow falha visivelmente: baixe o xlsx no site da Caixa, converta para `historico.csv` e use a aba **Dados**.

## Rodar local
`python -m http.server` na pasta e abra http://localhost:8000. Também funciona como CLI: `python lotosystem.py status`.
