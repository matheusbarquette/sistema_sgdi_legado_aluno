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

# 3. Banco e aplicação
python init_db.py
python app.py

# 4. (opcional, em outro terminal) gera tráfego para popular o dashboard
python gerar_trafego.py
```

| O quê | Onde |
|---|---|
| SGDI | http://localhost:5000 |
| Grafana | http://localhost:3000 (entra direto como admin) |
| Dashboard do projeto | Grafana → *Dashboards* → pasta **SGDI** → **SGDI — Observabilidade** |

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
| **Trace** | *Por onde a requisição passou e onde demorou?* | `GET /buscar` → `buscar_demandas` → `SELECT` | Tempo |

O **OpenTelemetry (OTel)** é o padrão aberto (da CNCF) para *gerar e enviar* esses sinais.
Ele não guarda nem desenha nada — só padroniza a coleta. Por isso dá para trocar o backend
(Grafana, Datadog, New Relic, Elastic...) sem mexer no código da aplicação.

## Arquitetura

```
┌──────────────────────┐   OTLP/HTTP :4318   ┌───────────────── grafana/otel-lgtm ─────────────────┐
│  Flask (app.py)      │ ──────────────────► │  OpenTelemetry Collector                             │
│  + telemetry.py      │   traces            │      ├── traces   ──► Tempo                          │
│                      │   métricas          │      ├── métricas ──► Prometheus                     │
│  OTel SDK            │   logs              │      └── logs     ──► Loki                           │
└──────────────────────┘                     │  Grafana :3000  (lê os três e monta o dashboard)    │
                                             └──────────────────────────────────────────────────────┘
```

O `docker-compose.yml` sobe a imagem **[grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm)**,
que empacota tudo em um container só (LGTM = **L**oki, **G**rafana, **T**empo, **M**imir/Prometheus).
É ótima para estudo e desenvolvimento local; em produção cada peça roda separada.

## Arquivos desta branch

| Arquivo | Para que serve |
|---|---|
| `docker-compose.yml` | Sobe o `grafana/otel-lgtm` e monta o dashboard do SGDI |
| `telemetry.py` | Configura o OTel: Resource, exportadores, logging e auto-instrumentação |
| `app.py` | Recebeu spans manuais, métricas de negócio e logs estruturados |
| `observabilidade/grafana/` | Provisionamento + JSON do dashboard **SGDI — Observabilidade** |
| `gerar_trafego.py` | Simula usuários (inclusive erros) para o dashboard ter o que mostrar |

## Como o OpenTelemetry foi ligado no Flask (`telemetry.py`)

São quatro passos. Todos acontecem uma vez, quando a aplicação sobe.

### 1. Resource — o "crachá" da aplicação

```python
resource = Resource.create({
    "service.name": "sgdi",
    "service.version": "1.0.0",
    "deployment.environment": "dev",
})
```

Tudo que o SGDI emitir carrega esses atributos. É assim que, no Grafana, filtramos `service_name="sgdi"`
mesmo quando houver 50 sistemas mandando dados para o mesmo lugar.

### 2. Providers + exportadores (um para cada sinal)

```python
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=".../v1/traces")))

leitor = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=".../v1/metrics"), export_interval_millis=5000)
metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[leitor]))

logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=".../v1/logs")))
```

- **Batch**: os dados são acumulados e enviados em lotes, numa thread separada — a requisição do usuário não espera.
- **Métricas** são lidas e enviadas a cada 5 s (o padrão é 60 s; diminuímos para a aula ficar mais "ao vivo").
- O endereço vem de `OTEL_EXPORTER_OTLP_ENDPOINT` (padrão `http://localhost:4318`).

### 3. Ponte com o `logging` do Python

```python
handler_otel = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
logging.getLogger().addHandler(handler_otel)
```

A partir daqui, **qualquer** `logging.info(...)` da aplicação (e das bibliotecas) vira um log OpenTelemetry.
De brinde, o handler anexa o `trace_id` e o `span_id` da requisição em andamento — é isso que liga log ↔ trace.

### 4. Auto-instrumentação

```python
FlaskInstrumentor().instrument_app(app)   # 1 span por request + métricas HTTP
SQLite3Instrumentor().instrument()        # 1 span por query SQL
```

Sem escrever mais nada, ganhamos:

- um **span** para cada requisição (`GET /detalhes/<id>`), com método, rota, status;
- um **span filho** para cada `cursor.execute(...)` mostrando o SQL executado;
- a métrica **`http.server.request.duration`** (histograma) — de onde saem req/s, taxa de erro e latência (p50/p95/p99).

> Usamos as convenções semânticas HTTP **estáveis** (`OTEL_SEMCONV_STABILITY_OPT_IN=http`), por isso no
> Prometheus a métrica aparece como `http_server_request_duration_seconds_*`.

## Exemplos adicionados no código (`app.py`)

A auto-instrumentação mostra *o técnico* (HTTP, SQL). O que é **do negócio** a gente instrumenta na mão.

### Trace — span manual

```python
@app.route('/buscar')
def buscar():
    termo = request.args.get('q')
    with tracer.start_as_current_span('buscar_demandas') as span:
        span.set_attribute('busca.termo', termo or '')
        ...
        resultados = cursor.execute(...).fetchall()
        span.set_attribute('busca.resultados', len(resultados))
```

No Tempo, a requisição vira uma cascata:

```
GET /buscar                    6 ms   ← FlaskInstrumentor
└── buscar_demandas            0,5 ms ← span manual (com busca.termo e busca.resultados)
    └── SELECT                 0,3 ms ← SQLite3Instrumentor
```

O mesmo foi feito em `nova_demanda` (span `salvar_demanda`, com título e solicitante).

### Métricas — counter, histograma e gauge

```python
demandas_criadas = meter.create_counter('sgdi.demandas.criadas', unit='1', description='Demandas criadas')
buscas_realizadas = meter.create_counter('sgdi.buscas', unit='1', description='Buscas realizadas')
resultados_busca = meter.create_histogram('sgdi.busca.resultados', unit='1', description='Quantidade de resultados por busca')

# dentro das rotas
demandas_criadas.add(1)
buscas_realizadas.add(1, {'com_resultado': len(resultados) > 0})   # atributo vira label
resultados_busca.record(len(resultados))
```

E dois **gauges observáveis** — em vez de a rota avisar, o SDK *pergunta* o valor a cada 5 s:

```python
def observar_comentarios_orfaos(options):
    yield Observation(_contar('SELECT COUNT(*) FROM comentarios WHERE demanda_id NOT IN (...)'))

meter.create_observable_gauge('sgdi.comentarios.orfaos', callbacks=[observar_comentarios_orfaos])
```

| Tipo | Quando usar | Métricas no SGDI (nome no Prometheus) |
|---|---|---|
| **Counter** | algo que só aumenta (eventos) | `sgdi_demandas_criadas_total`, `sgdi_demandas_deletadas_total`, `sgdi_comentarios_criados_total`, `sgdi_buscas_total` |
| **Histogram** | distribuição de valores (tempo, tamanho) | `sgdi_busca_resultados_*`, `http_server_request_duration_seconds_*` |
| **Gauge** | "foto" de um valor que sobe e desce | `sgdi_demandas_total`, `sgdi_comentarios_orfaos` |

Repare que o Prometheus troca `.` por `_` e acrescenta `_total` nos counters.

> **Cuidado com cardinalidade:** atributo de métrica vira *label*, e cada combinação de labels vira uma série
> nova no Prometheus. `com_resultado` (true/false) é ok; `termo` ou `solicitante` **não** — esses vão no log ou no span.

### Logs estruturados — o argumento `extra` do `logging`

```python
logger = logging.getLogger('sgdi')

logger.info('Demanda criada', extra={
    'evento': 'demanda_criada',
    'demanda_titulo': titulo,
    'solicitante': solicitante,
})

logger.warning('Tentativa de deletar demanda inexistente', extra={
    'evento': 'demanda_nao_encontrada', 'demanda_id': id})
```

O `extra` é um recurso **nativo** do `logging` do Python: cada chave vira um atributo do `LogRecord`.
O `LoggingHandler` do OpenTelemetry pega esses atributos e os envia como **campos do log**. Resultado no Loki:

```
Demanda criada
  evento          = demanda_criada
  solicitante     = Ana
  demanda_titulo  = Demanda gerada 12
  severity_text   = INFO
  trace_id        = 487adb7a6d9e982add1371229b8ae264   ← colocado automaticamente
  span_id         = 3be8dbd2579474b0
  code_function_name = nova_demanda
```

Por que isso é melhor do que `logger.info(f'Demanda {titulo} criada por {solicitante}')`?
Porque dá para **filtrar e agregar** sem regex:

```logql
{service_name="sgdi"} | evento="demanda_criada" | solicitante="Ana"
sum by (evento) (count_over_time({service_name="sgdi"} | evento != "" [5m]))
```

Eventos registrados: `demanda_criada`, `demanda_editada`, `demanda_deletada`, `demanda_nao_encontrada`,
`comentario_criado`, `busca`. Exceções não tratadas (ex.: `/editar/abc`) chegam como `ERROR` com o traceback completo.

### Dois ajustes que valem uma explicação

- `app.config['PROPAGATE_EXCEPTIONS'] = False` — com `debug=True` o Flask joga a exceção para o debugger do
  Werkzeug e a instrumentação nunca vê o 500. Com essa linha o Flask responde 500 "de verdade": o erro entra
  na métrica, o span fica vermelho e o traceback vai para o Loki.
- `app.run(..., use_reloader=False)` — o reloader do modo debug sobe **dois** processos, e a telemetria sairia duplicada.

## O dashboard "SGDI — Observabilidade"

Fica em `observabilidade/grafana/dashboards/sgdi.json` e é carregado automaticamente pelo Grafana.

| Linha | O que mostra |
|---|---|
| 📋 **Negócio** | demandas cadastradas, criadas, deletadas, comentários, buscas, **comentários órfãos**, buscas com/sem resultado |
| 🚦 **Saúde HTTP (RED)** | **R**ate (req/s), **E**rrors (% de 5xx), **D**uration (p50/p95/p99), tudo também por rota |
| 📜 **Logs** | volume por `evento`, volume por nível, e o stream de logs filtrável pelas variáveis no topo |
| 🧵 **Traces** | traces recentes e traces com erro — clique no Trace ID para ver a cascata |

Filtros no topo: **Rota** (painéis HTTP), **Nível do log** e **Evento** (painel de logs).

### Roteiro de demonstração

1. Rode `python gerar_trafego.py` e abra o dashboard.
2. O painel **Erros 5xx por rota** acusa `/editar/<id>`. Por quê?
3. Em **Traces com erro**, abra um trace: o span do `SELECT` mostra `WHERE id=abc` — SQL concatenado!
4. No painel de logs, filtre **Nível = ERROR**: está lá o `sqlite3.OperationalError`. Clique no log → link do `trace_id` → cai no mesmo trace.
5. **Comentários órfãos** está vermelho: a tabela não tem FOREIGN KEY e deletar uma demanda deixa comentários soltos.

Ou seja: os problemas do legado viraram **números, gráficos e evidências**. É isso que observabilidade entrega.

## Dicas e problemas comuns

- **Não aparece nada no Grafana?** Confira se o container está de pé (`docker compose ps`) e espere uns 30 s
  na primeira subida. Métricas chegam a cada 5 s; logs e traces em lote, em poucos segundos.
- **Editou o JSON do dashboard e nada mudou?** No Windows o Docker nem sempre avisa o Grafana da mudança: `docker compose restart`.
- **Apontar para outro coletor:** `set OTEL_EXPORTER_OTLP_ENDPOINT=http://outro-host:4318` (Linux/Mac: `export ...`).
- **Zerar tudo:** `docker compose down -v` apaga também os dados guardados de métricas, logs e traces.

---

**TODO:**
- Adicionar prioridades
- Melhorar busca
- Adicionar usuários

---

*Desenvolvido em 2024 · instrumentado com OpenTelemetry em 2026*
