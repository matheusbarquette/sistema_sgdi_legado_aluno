# SGDI - Sistema de Gestão de Demandas Internas

Sistema para gerenciar demandas internas da empresa.

> ⚠️ Este é um **sistema legado de propósito** (SQL concatenado, `secret_key` fixa, tabela sem chave primária...).
> Nesta branch ele **não foi corrigido**: ele foi **instrumentado com OpenTelemetry** para que a gente
> consiga *enxergar* esses problemas acontecendo em produção.

## Como rodar

```bash
# 1. Sobe a stack de observabilidade (Grafana + Prometheus + Loki + Tempo + OTel Collector)
docker compose up -d

# 2. Ambiente Python
python -m venv venv
venv\Scripts\activate          # Windows  (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt

# 3. Banco e aplicação — repare: o app é iniciado PELO opentelemetry-instrument
python init_db.py
opentelemetry-instrument --service_name sgdi --exporter_otlp_protocol http/protobuf --metric_export_interval 5000 --semconv_stability_opt_in http python app.py

# 4. (opcional, em outro terminal) gera tráfego para popular o dashboard
python gerar_trafego.py
```

| O quê | Onde |
|---|---|
| SGDI | http://localhost:5000 |
| Grafana | http://localhost:3000 (entra direto como admin) |
| Dashboard do projeto | Grafana → *Dashboards* → pasta **SGDI** → **SGDI — Observabilidade** |

> Rodou só `python app.py`? O sistema funciona normalmente, mas **nada** chega no Grafana:
> quem liga a telemetria é o `opentelemetry-instrument`.

## Funcionalidades

- Criar demandas
- Editar demandas
- Deletar demandas
- Visualizar detalhes
- Comentários

---

# 🔭 Observabilidade com OpenTelemetry

## A ideia em 30 segundos

Observabilidade é conseguir responder **"o que está acontecendo no meu sistema agora, e por quê?"**
sem precisar abrir o código nem colocar `print` em produção. Para isso a aplicação emite três tipos de sinal:

| Sinal | Pergunta que responde | Exemplo no SGDI | Vai para |
|---|---|---|---|
| **Métrica** | *Quanto? Com que frequência? Está piorando?* | 1,4 req/s, p95 = 18 ms, 1,5% de erro | Prometheus |
| **Log** | *O que aconteceu exatamente neste momento?* | `Demanda criada` com `solicitante=Ana` | Loki |
| **Trace** | *Por onde a requisição passou e onde demorou?* | `GET /buscar` → `SELECT` | Tempo |

O **OpenTelemetry (OTel)** é o padrão aberto (da CNCF) para *gerar e enviar* esses sinais.
Ele não guarda nem desenha nada — só padroniza a coleta. Por isso dá para trocar o backend
(Grafana, Datadog, New Relic, Elastic...) sem mexer no código da aplicação.

## Duas formas de instrumentar

| | **Opção 1 — Automática** (usada neste código) | **Opção 2 — Manual** (só no README) |
|---|---|---|
| Como liga | `opentelemetry-instrument python app.py` | um `telemetry.py` chamado pelo `app.py` |
| Código OTel no projeto | **nenhum** | ~90 linhas de configuração + spans/métricas nas rotas |
| Traces HTTP + SQL | ✅ | ✅ |
| Métricas HTTP (req/s, erro, latência) | ✅ | ✅ |
| Logs com `trace_id` | ✅ (do `logging` padrão) | ✅ |
| Spans e métricas **de negócio** | ❌ | ✅ |

A **Opção 1** é a que está no código: vocês conseguem levar para o projeto de vocês
**sem criar nenhum arquivo novo** — basta instalar os pacotes e mudar o comando que sobe a aplicação.
A **Opção 2** está documentada [no fim deste README](#-opção-2--instrumentação-manual-referência) para quem
quiser ver o que acontece "por baixo dos panos" ou precisar de métricas de negócio.

## Arquitetura

```
┌──────────────────────────────┐  OTLP/HTTP :4318  ┌───────────────── grafana/otel-lgtm ─────────────────┐
│  opentelemetry-instrument    │ ────────────────► │  OpenTelemetry Collector                             │
│   └── python app.py (Flask)  │   traces          │      ├── traces   ──► Tempo                          │
│                              │   métricas        │      ├── métricas ──► Prometheus                     │
│  OTel SDK + instrumentações  │   logs            │      └── logs     ──► Loki                           │
└──────────────────────────────┘                   │  Grafana :3000  (lê os três e monta o dashboard)    │
                                                   └──────────────────────────────────────────────────────┘
```

O `docker-compose.yml` sobe a imagem **[grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm)**,
que empacota tudo em um container só (LGTM = **L**oki, **G**rafana, **T**empo, **M**imir/Prometheus).
É ótima para estudo e desenvolvimento local; em produção cada peça roda separada.

## Arquivos desta branch

| Arquivo | Para que serve |
|---|---|
| `requirements.txt` | Pacotes do OTel: `opentelemetry-distro` (traz o comando `opentelemetry-instrument`), exportador e instrumentações |
| `app.py` | **Sem nenhum import do OpenTelemetry** — só ganhou logs com o `logging` padrão e dois ajustes do Flask |
| `docker-compose.yml` | Sobe o `grafana/otel-lgtm` e monta o dashboard do SGDI |
| `observabilidade/grafana/` | Provisionamento + JSON do dashboard **SGDI — Observabilidade** |
| `gerar_trafego.py` | Simula usuários (inclusive erros) para o dashboard ter o que mostrar |

---

# ⚡ Opção 1 — Instrumentação automática (a que está no código)

## O que o `opentelemetry-instrument` faz

```
opentelemetry-instrument [opções] python app.py
```

Antes de o `app.py` rodar, ele:

1. **Configura o SDK** — cria os providers de traces, métricas e logs e os exportadores OTLP
   (tudo que, na Opção 2, a gente escreve à mão no `telemetry.py`);
2. **Procura as instrumentações instaladas** (`opentelemetry-instrumentation-*`) e liga cada uma.
   Elas fazem *monkey patching*: trocam funções do Flask, do `sqlite3` e do `logging` por versões que geram telemetria;
3. **Executa o `python app.py`** normalmente.

Com o que está no `requirements.txt`, ganhamos sem escrever nenhuma linha:

| Instrumentação | O que gera |
|---|---|
| `opentelemetry-instrumentation-flask` | 1 **span** por request (`GET /detalhes/<id>`, com método, rota, status) e a métrica **`http.server.request.duration`** (de onde saem req/s, taxa de erro e p50/p95/p99) |
| `opentelemetry-instrumentation-sqlite3` | 1 **span filho** por `cursor.execute(...)`, com o SQL executado em `db.statement` |
| `opentelemetry-instrumentation-logging` | todo `logging.info/warning/error(...)` vira **log OTel**, já com `trace_id` e `span_id` |

No Tempo, uma requisição vira uma cascata:

```
GET /buscar                    6 ms   ← instrumentação do Flask
└── SELECT                     0,3 ms ← instrumentação do sqlite3 (db.statement = "SELECT * FROM demandas WHERE titulo LIKE '%bug%'")
```

## As opções do comando

Cada opção `--xxx` do `opentelemetry-instrument` equivale a uma variável de ambiente `OTEL_XXX`
(use a que preferir):

| Opção | Variável de ambiente | Por quê |
|---|---|---|
| `--service_name sgdi` | `OTEL_SERVICE_NAME` | O "crachá" da aplicação. É por ele que filtramos `service_name="sgdi"` no Grafana |
| `--exporter_otlp_protocol http/protobuf` | `OTEL_EXPORTER_OTLP_PROTOCOL` | O padrão do Python é gRPC (porta 4317); usamos HTTP (porta 4318), que não precisa do pacote `grpcio` |
| `--metric_export_interval 5000` | `OTEL_METRIC_EXPORT_INTERVAL` | Envia métricas a cada 5 s (o padrão é 60 s) — a aula fica mais "ao vivo" |
| `--semconv_stability_opt_in http` | `OTEL_SEMCONV_STABILITY_OPT_IN` | Usa as convenções HTTP **estáveis**: a métrica sai como `http_server_request_duration_seconds_*`, que é o que o dashboard consulta |
| `--exporter_otlp_endpoint http://outro-host:4318` | `OTEL_EXPORTER_OTLP_ENDPOINT` | Opcional. O padrão já é `http://localhost:4318` |

Exemplo usando variáveis de ambiente no **PowerShell**:

```powershell
$env:OTEL_SERVICE_NAME = "sgdi"
$env:OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"
$env:OTEL_METRIC_EXPORT_INTERVAL = "5000"
$env:OTEL_SEMCONV_STABILITY_OPT_IN = "http"
opentelemetry-instrument python app.py
```

O mesmo no **Prompt de Comando (cmd)** do Windows:

```bat
set OTEL_SERVICE_NAME=sgdi
set OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
set OTEL_METRIC_EXPORT_INTERVAL=5000
set OTEL_SEMCONV_STABILITY_OPT_IN=http
opentelemetry-instrument python app.py
```

> No cmd **não** coloque espaço nem aspas em volta do `=` (`set NOME=valor`): senão o espaço/aspas viram parte do nome ou do valor.
> Nos dois casos as variáveis valem só para aquela janela do terminal — abriu outra, precisa definir de novo.

## Levando para o projeto de vocês (3 passos)

```bash
# 1. Instale o distro (traz o comando opentelemetry-instrument) e o exportador
pip install opentelemetry-distro opentelemetry-exporter-otlp-proto-http

# 2. Deixe o OTel descobrir as bibliotecas do projeto e instalar as instrumentações certas
opentelemetry-bootstrap -a install

# 3. Suba a aplicação através dele
opentelemetry-instrument --service_name meu-projeto --exporter_otlp_protocol http/protobuf python app.py
```

O `opentelemetry-bootstrap -a requirements` só **lista** os pacotes, sem instalar — útil para colar no `requirements.txt`.

## Logs estruturados — o argumento `extra` do `logging`

A única coisa adicionada nas rotas do `app.py` foram logs, usando **só o `logging` padrão do Python**:

```python
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s - %(message)s')
logger = logging.getLogger('sgdi')

logger.info('Demanda criada', extra={
    'evento': 'demanda_criada',
    'demanda_titulo': titulo,
    'solicitante': solicitante,
})

logger.warning('Tentativa de deletar demanda inexistente', extra={
    'evento': 'demanda_nao_encontrada', 'demanda_id': id})
```

- O `basicConfig(level=logging.INFO)` é necessário porque o Python, por padrão, só deixa passar `WARNING` para cima.
- O `extra` é um recurso **nativo** do `logging`: cada chave vira um atributo do `LogRecord`.
  A instrumentação de logging do OTel pega esses atributos e os envia como **campos do log**. Resultado no Loki:

```
Demanda criada
  evento          = demanda_criada
  solicitante     = Ana
  demanda_titulo  = Demanda gerada 12
  severity_text   = INFO
  trace_id        = 487adb7a6d9e982add1371229b8ae264   ← colocado automaticamente
  span_id         = 3be8dbd2579474b0
```

Por que isso é melhor do que `logger.info(f'Demanda {titulo} criada por {solicitante}')`?
Porque dá para **filtrar e agregar** sem regex — e até tirar **números de negócio** dos logs:

```logql
{service_name="sgdi"} | evento="demanda_criada" | solicitante="Ana"
sum by (evento) (count_over_time({service_name="sgdi"} | evento != "" [5m]))
```

É assim que a linha **📋 Negócio** do dashboard funciona sem nenhuma métrica customizada: ela conta os logs
por `evento` no Loki.

Eventos registrados: `demanda_criada`, `demanda_editada`, `demanda_deletada`, `demanda_nao_encontrada`,
`comentario_criado`, `busca`. Exceções não tratadas (ex.: `/editar/abc`) chegam como `ERROR` com o traceback completo.

## Dois ajustes que valem uma explicação

- `app.config['PROPAGATE_EXCEPTIONS'] = False` — com `debug=True` o Flask joga a exceção para o debugger do
  Werkzeug e a instrumentação nunca vê o 500. Com essa linha o Flask responde 500 "de verdade": o erro entra
  na métrica, o span fica vermelho e o traceback vai para o Loki.
- `app.run(..., use_reloader=False)` — o reloader do modo debug sobe **dois** processos, e a telemetria sairia duplicada.

## O dashboard "SGDI — Observabilidade"

Fica em `observabilidade/grafana/dashboards/sgdi.json` e é carregado automaticamente pelo Grafana.

| Linha | O que mostra | Fonte |
|---|---|---|
| 📋 **Negócio** | demandas criadas, deletadas, comentários, buscas, buscas com/sem resultado, média de resultados | logs (Loki) |
| 🚦 **Saúde HTTP (RED)** | **R**ate (req/s), **E**rrors (% de 5xx), **D**uration (p50/p95/p99), tudo também por rota | métricas automáticas (Prometheus) |
| 📜 **Logs** | volume por `evento`, volume por nível, e o stream de logs filtrável pelas variáveis no topo | Loki |
| 🧵 **Traces** | traces recentes e traces com erro — clique no Trace ID para ver a cascata | Tempo |

Os cards **Demandas cadastradas** e **Comentários órfãos** mostram *"só manual"*: eles dependem de
gauges que só existem na [Opção 2](#-opção-2--instrumentação-manual-referência).

Filtros no topo: **Rota** (painéis HTTP), **Nível do log** e **Evento** (painel de logs).

### Roteiro de demonstração

1. Rode `python gerar_trafego.py` e abra o dashboard.
2. O painel **Erros 5xx por rota** acusa `/editar/<id>`. Por quê?
3. Em **Traces com erro**, abra um trace: o span do `SELECT` mostra `WHERE id=abc` — SQL concatenado!
4. No painel de logs, filtre **Nível = ERROR**: está lá o `sqlite3.OperationalError`. Clique no log → link do `trace_id` → cai no mesmo trace.
5. **Buscas: com vs. sem resultado** mostra quantos usuários não acham o que procuram — o TODO *"Melhorar busca"* virou dado.
6. *(Com a Opção 2)* **Comentários órfãos** fica vermelho: a tabela não tem FOREIGN KEY e deletar uma demanda deixa comentários soltos.

Ou seja: os problemas do legado viraram **números, gráficos e evidências** — sem uma linha de OpenTelemetry no código.

---

# 🛠️ Opção 2 — Instrumentação manual (referência)

> Isto **não** está no código dos alunos. É o mesmo resultado da Opção 1, só que configurado à mão,
> mais as métricas e spans **de negócio** que a instrumentação automática não tem como adivinhar.
> Útil para mostrar o que o `opentelemetry-instrument` faz por baixo dos panos.

## O que muda

1. `requirements.txt`: troque o `opentelemetry-distro` por `opentelemetry-sdk` (e mantenha exportador + instrumentações):

   ```
   opentelemetry-api==1.45.1
   opentelemetry-sdk==1.45.1
   opentelemetry-exporter-otlp-proto-http==1.45.1
   opentelemetry-instrumentation-flask==0.66b1
   opentelemetry-instrumentation-sqlite3==0.66b1
   ```

2. Crie o `telemetry.py` (abaixo) e chame-o no `app.py`.
3. Suba **sem** o `opentelemetry-instrument`: `python app.py`.

## `telemetry.py` — os quatro passos que o `opentelemetry-instrument` faz sozinho

```python
import logging
import os

# Usa as convenções semânticas HTTP estáveis (ex.: métrica http.server.request.duration).
# Precisa ser definido ANTES de importar a instrumentação do Flask.
os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "sgdi")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")


def configurar_telemetria(app):
    # 1. Resource = "crachá" da aplicação: vai junto em todo trace, métrica e log.
    resource = Resource.create({
        "service.name": SERVICE_NAME,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("AMBIENTE", "dev"),
    })

    # 2. Providers + exportadores, um para cada sinal
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTLP_ENDPOINT}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    leitor = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{OTLP_ENDPOINT}/v1/metrics"),
        export_interval_millis=5000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[leitor]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{OTLP_ENDPOINT}/v1/logs"))
    )
    set_logger_provider(logger_provider)

    # 3. Ponte com o logging do Python: todo logging.info(...) vira um log OTel,
    #    com os campos do extra={...} e o trace_id/span_id do request atual.
    handler_otel = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    # O access log do werkzeug ("GET / 200") só repete o que o trace já mostra: fica só no console.
    handler_otel.addFilter(lambda registro: registro.name != "werkzeug")
    handler_console = logging.StreamHandler()
    handler_console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(handler_otel)
    raiz.addHandler(handler_console)

    # 4. Instrumentações: o que o opentelemetry-instrument descobre e liga sozinho
    FlaskInstrumentor().instrument_app(app)   # 1 span por request + métricas HTTP
    SQLite3Instrumentor().instrument()        # 1 span por query SQL

    return trace.get_tracer("sgdi"), metrics.get_meter("sgdi")
```

- **Batch**: os dados são acumulados e enviados em lotes, numa thread separada — a requisição do usuário não espera.
- Repare que *tudo* isso é o que as opções `--service_name`, `--exporter_otlp_protocol`, `--metric_export_interval`
  e `--semconv_stability_opt_in` da Opção 1 resolvem.

No `app.py`, troque o `logging.basicConfig(...)` por:

```python
from telemetry import configurar_telemetria

tracer, meter = configurar_telemetria(app)
logger = logging.getLogger('sgdi')
```

## Spans manuais — pedaços do negócio dentro do trace

```python
@app.route('/buscar')
def buscar():
    termo = request.args.get('q')
    with tracer.start_as_current_span('buscar_demandas') as span:
        span.set_attribute('busca.termo', termo or '')
        conn = sqlite3.connect('demandas.db')
        cursor = conn.cursor()
        resultados = cursor.execute(f"SELECT * FROM demandas WHERE titulo LIKE '%{termo}%'").fetchall()
        conn.close()
        span.set_attribute('busca.resultados', len(resultados))
    ...
```

A cascata no Tempo ganha um nível a mais:

```
GET /buscar                    6 ms   ← FlaskInstrumentor
└── buscar_demandas            0,5 ms ← span manual (com busca.termo e busca.resultados)
    └── SELECT                 0,3 ms ← SQLite3Instrumentor
```

Dá para fazer o mesmo em `nova_demanda` (span `salvar_demanda`, com título e solicitante).

> Os spans manuais também funcionam **junto** com a Opção 1: basta `from opentelemetry import trace`
> e `tracer = trace.get_tracer('sgdi')` no `app.py` — o `opentelemetry-instrument` já configurou o resto.

## Métricas de negócio — counter, histograma e gauge

```python
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.metrics import Observation

demandas_criadas = meter.create_counter('sgdi.demandas.criadas', unit='1', description='Demandas criadas')
demandas_deletadas = meter.create_counter('sgdi.demandas.deletadas', unit='1', description='Demandas deletadas')
comentarios_criados = meter.create_counter('sgdi.comentarios.criados', unit='1', description='Comentários adicionados')
buscas_realizadas = meter.create_counter('sgdi.buscas', unit='1', description='Buscas realizadas')
resultados_busca = meter.create_histogram('sgdi.busca.resultados', unit='1', description='Quantidade de resultados por busca')

# dentro das rotas
demandas_criadas.add(1)
buscas_realizadas.add(1, {'com_resultado': len(resultados) > 0})   # atributo vira label
resultados_busca.record(len(resultados))
```

E dois **gauges observáveis** — em vez de a rota avisar, o SDK *pergunta* o valor a cada 5 s.
São eles que acendem os cards **Demandas cadastradas** e **Comentários órfãos** do dashboard:

```python
def _contar(sql):
    # suppress_instrumentation: não gera span para as queries de coleta de métrica
    with suppress_instrumentation():
        conn = sqlite3.connect('demandas.db')
        total = conn.execute(sql).fetchone()[0]
        conn.close()
    return total


def observar_estoque(options):
    yield Observation(_contar('SELECT COUNT(*) FROM demandas'))


def observar_comentarios_orfaos(options):
    yield Observation(_contar(
        'SELECT COUNT(*) FROM comentarios WHERE demanda_id NOT IN (SELECT id FROM demandas WHERE id IS NOT NULL)'))


meter.create_observable_gauge('sgdi.demandas.total', callbacks=[observar_estoque],
                              description='Demandas cadastradas no banco')
meter.create_observable_gauge('sgdi.comentarios.orfaos', callbacks=[observar_comentarios_orfaos],
                              description='Comentários ligados a demandas que não existem')
```

| Tipo | Quando usar | Métricas no SGDI (nome no Prometheus) |
|---|---|---|
| **Counter** | algo que só aumenta (eventos) | `sgdi_demandas_criadas_total`, `sgdi_demandas_deletadas_total`, `sgdi_comentarios_criados_total`, `sgdi_buscas_total` |
| **Histogram** | distribuição de valores (tempo, tamanho) | `sgdi_busca_resultados_*`, `http_server_request_duration_seconds_*` |
| **Gauge** | "foto" de um valor que sobe e desce | `sgdi_demandas_total`, `sgdi_comentarios_orfaos` |

Repare que o Prometheus troca `.` por `_` e acrescenta `_total` nos counters.

> **Cuidado com cardinalidade:** atributo de métrica vira *label*, e cada combinação de labels vira uma série
> nova no Prometheus. `com_resultado` (true/false) é ok; `termo` ou `solicitante` **não** — esses vão no log ou no span.

### Contar pelo log ou por métrica?

Na Opção 1 a linha **Negócio** conta logs no Loki; na Opção 2 dá para usar os counters no Prometheus
(ex.: `sum(increase(sgdi_demandas_criadas_total{job="sgdi"}[$__range]))`). Métrica é mais barata de guardar
e consultar por meses; log é mais flexível (dá para filtrar por `solicitante`, por exemplo). Em sistemas grandes,
o normal é ter os dois.

---

## Dicas e problemas comuns

- **Não aparece nada no Grafana?** Confira se subiu com `opentelemetry-instrument ... python app.py` (e não só `python app.py`),
  se o container está de pé (`docker compose ps`) e espere uns 30 s na primeira subida.
  Métricas chegam a cada 5 s; logs e traces em lote, em poucos segundos.
- **Painéis HTTP vazios, mas traces chegando?** Faltou o `--semconv_stability_opt_in http`: sem ele a métrica sai com o
  nome antigo (`http_server_duration_milliseconds_*`) e o dashboard não encontra.
- **Erro de conexão na porta 4317?** Faltou o `--exporter_otlp_protocol http/protobuf` (o padrão é gRPC).
- **Editou o JSON do dashboard e nada mudou?** No Windows o Docker nem sempre avisa o Grafana da mudança: `docker compose restart`.
- **Apontar para outro coletor:** `--exporter_otlp_endpoint http://outro-host:4318` (ou a variável `OTEL_EXPORTER_OTLP_ENDPOINT`).
- **Zerar tudo:** `docker compose down -v` apaga também os dados guardados de métricas, logs e traces.

---

**TODO:**
- Adicionar prioridades
- Melhorar busca
- Adicionar usuários

---

*Desenvolvido em 2024 · instrumentado com OpenTelemetry em 2026*
