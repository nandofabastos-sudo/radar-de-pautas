# Radar de Pautas — protótipo Remo

Sistema que monitora fontes "primeira mão" do Clube do Remo (YouTube + sites)
e te avisa no WhatsApp assim que sai notícia nova. Esse é o protótipo-matriz:
depois de validado, é só copiar o padrão pra Paysandu, Goiás, Vila Nova e CRB.

## O que já está pronto

- `config.json` — lista de fontes do Remo (3 canais de YouTube, o agregador
  Remo 100% via RSS, e o site oficial + DOL via scraping leve).
- `monitor.py` — checa cada fonte, compara com o que já foi visto
  (`state/state.json`) e dispara WhatsApp só do que é novo.
- `.github/workflows/monitor.yml` — roda o `monitor.py` a cada 10 minutos, de
  graça, via GitHub Actions (não precisa de servidor seu rodando 24h).

Duas fontes que você mandou **ainda não entraram** no automático:
- **Remistas** — o site tem proteção anti-bot ativa; bloqueou até minha
  tentativa de leitura simples. Dá pra tentar contornar com um serviço de
  scraping pago (tipo Apify), mas por ora fica de fora.
- **ge.globo.com** — domínio da Globo bloqueia acesso automatizado e não tem
  RSS público. Mesma situação.

Isso significa que essas duas, por enquanto, ficam pra checagem manual sua
mesmo (ou a gente revisita depois se fizer diferença real no resultado).

## Passo a passo para colocar no ar

### 1. Criar sua conta no CallMeBot (o que manda a mensagem pro seu WhatsApp)

1. Salve o contato `+34 644 56 55 18` no seu celular.
2. Mande a mensagem `"I allow callmebot to send me messages"` pra esse
   contato, pelo WhatsApp.
3. Em poucos minutos ele responde com sua `apikey` (um número). Guarde ela e
   guarde também o seu número de telefone com código do país (ex:
   `5591999999999`).

   > É gratuito, mas é **só pra uso pessoal** — ele manda mensagem só pra
   > você mesmo, não serve pra distribuir pra outras pessoas.

### 2. Criar o repositório no GitHub

1. Crie um repositório novo (pode ser privado) e suba estes arquivos.
2. Em **Settings → Secrets and variables → Actions**, crie dois secrets:
   - `CALLMEBOT_PHONE` → seu número (ex: `5591999999999`)
   - `CALLMEBOT_APIKEY` → a apikey que o bot te mandou

### 3. Deixar rodando

O workflow já está configurado pra rodar sozinho a cada 10 minutos
(`.github/workflows/monitor.yml`). Você também pode disparar manualmente em
**Actions → Radar de Pautas → Run workflow**, pra testar.

**Importante:** na primeira execução, o sistema só grava o que já existe em
cada fonte — ele não te manda uma enxurrada de notificação de coisa antiga.
A partir da segunda execução em diante, só chega o que é realmente novo.

## Como adicionar os próximos clubes

Em `config.json`, os clubes `paysandu`, `goias`, `vila_nova` e `crb` já estão
com a estrutura pronta, só faltando preencher `"sources"` no mesmo formato do
Remo — me manda as fontes de cada um (canal oficial, sites, etc.) que eu
preencho e testo os padrões de scraping igual fiz com o Remo.

## Tipos de fonte suportados hoje

- `youtube_rss` / `rss` — feeds RSS (mais estável, recomendado sempre que
  existir).
- `scrape_list` — lista de notícias de um site sem RSS; usa um padrão de URL
  (regex) pra achar os links mais recentes na página de listagem, e procura
  a tag `<h1>`-`<h6>` mais próxima do link pra extrair o título real da
  notícia (com fallback pro nome da fonte, se não achar nada). Também
  corrige automaticamente sites que declaram o charset errado no
  `Content-Type` (causa comum de acento quebrado tipo "Ã³" em vez de "ó").

## Limitações a ter em mente

- Sites sem RSS podem mudar de estrutura e quebrar o scraping — se um dia
  parar de notificar algo específico, é provável que o site tenha mudado o
  HTML e o padrão precise de ajuste.
- CallMeBot é gratuito mas informal — se quiser algo de nível
  "produção/cliente" mais robusto no futuro, dá pra migrar pra WhatsApp
  Business API (Meta) sem mudar o resto do sistema.
