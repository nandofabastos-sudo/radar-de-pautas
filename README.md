# Radar de Pautas — protótipo Remo

Sistema que monitora fontes "primeira mão" do Clube do Remo (YouTube + sites)
e te avisa no Telegram assim que sai notícia nova. Esse é o protótipo-matriz:
depois de validado, é só copiar o padrão pra Paysandu, Goiás, Vila Nova e CRB.

## O que já está pronto

- `config.json` — lista de fontes do Remo (3 canais de YouTube, o agregador
  Remo 100% via RSS, e o site oficial + DOL via scraping leve).
- `monitor.py` — checa cada fonte, compara com o que já foi visto
  (`state/state.json`) e dispara Telegram só do que é novo.
- `.github/workflows/monitor.yml` — roda o `monitor.py` a cada 10 minutos, de
  graça, via GitHub Actions (não precisa de servidor seu rodando 24h).

> **Nota:** a ideia original era notificar por WhatsApp via CallMeBot (API
> gratuita não-oficial). O CallMeBot nunca respondeu com a apikey mesmo após
> passar do prazo de 24h que eles mesmos documentam como normal em caso de
> sobrecarga, então migramos para um bot do Telegram — oficial, gratuito e
> instantâneo. Se quiser tentar WhatsApp de novo no futuro (o CallMeBot pode
> voltar a funcionar, ou dá pra migrar pra WhatsApp Business API da Meta),
> a troca fica isolada na função `notify_telegram()` em `monitor.py`.

Duas fontes que você mandou **ainda não entraram** no automático:
- **Remistas** — o site tem proteção anti-bot ativa; bloqueou até minha
  tentativa de leitura simples. Dá pra tentar contornar com um serviço de
  scraping pago (tipo Apify), mas por ora fica de fora.
- **ge.globo.com** — domínio da Globo bloqueia acesso automatizado e não tem
  RSS público. Mesma situação.

Isso significa que essas duas, por enquanto, ficam pra checagem manual sua
mesmo (ou a gente revisita depois se fizer diferença real no resultado).

## Passo a passo para colocar no ar

### 1. Criar seu bot no Telegram (o que manda a mensagem pra você)

1. No Telegram, procure **@BotFather** e envie `/newbot`.
2. Escolha um nome e um username (precisa terminar em `bot`).
3. O BotFather responde na hora com um **token** (formato
   `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`). Guarde esse token.
4. Abra uma conversa com o bot que você acabou de criar e mande qualquer
   mensagem pra ele (ex: "oi") — isso é necessário pra ele conseguir te
   responder depois.
5. Descubra seu `chat_id` acessando esta URL no navegador (troca `<TOKEN>`
   pelo token do passo 3):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Procure por `"chat":{"id":123456789,...}` na resposta — esse número é
   o seu `chat_id`.

   > É gratuito e oficial — o bot manda mensagem só pra você mesmo (ou pra
   > quem você adicionar depois num grupo, se quiser).

### 2. Criar o repositório no GitHub

1. Crie um repositório novo (pode ser privado) e suba estes arquivos.
2. Em **Settings → Secrets and variables → Actions**, crie dois secrets:
   - `TELEGRAM_BOT_TOKEN` → o token que o BotFather te deu
   - `TELEGRAM_CHAT_ID` → o chat_id que você descobriu no passo 5

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
- `json_list` — site que serve as notícias por uma API em JSON (caso do
  Paysandu). É o mais estável dos três: não depende do HTML, que muda.
  Precisa de `items_path` (caminho até a lista, ex: `results.noticias`),
  `id_field`, `title_field` e `link_template` (molde do link, com os campos
  do item entre chaves — ex: `.../noticias/{id}/{slug}`).

## Limitações a ter em mente

- Sites sem RSS podem mudar de estrutura e quebrar o scraping — se um dia
  parar de notificar algo específico, é provável que o site tenha mudado o
  HTML e o padrão precise de ajuste.
- A notificação hoje chega no Telegram, não no WhatsApp. Se no futuro isso
  fizer diferença real (ex: querer ver no WhatsApp mesmo), dá pra trocar de
  novo mexendo só na função `notify_telegram()` em `monitor.py`.
