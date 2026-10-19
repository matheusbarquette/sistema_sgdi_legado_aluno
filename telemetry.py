"""
Configuração do OpenTelemetry para o SGDI.

Este módulo liga os três sinais de observabilidade e manda tudo, via OTLP/HTTP,
para o coletor do container grafana/otel-lgtm (porta 4318):

    - Traces   -> Tempo
    - Métricas -> Prometheus
    - Logs     -> Loki

Uso (em app.py):

    from telemetry import configurar_telemetria
    tracer, meter = configurar_telemetria(app)
"""
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
    # Resource = "crachá" da aplicação: vai junto em todo trace, métrica e log.
    resource = Resource.create({
        "service.name": SERVICE_NAME,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("AMBIENTE", "dev"),
    })

    # ---------- TRACES ----------
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTLP_ENDPOINT}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    # ---------- MÉTRICAS ----------
    leitor = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{OTLP_ENDPOINT}/v1/metrics"),
        export_interval_millis=5000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[leitor]))

    # ---------- LOGS ----------
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{OTLP_ENDPOINT}/v1/logs"))
    )
    set_logger_provider(logger_provider)

    # O LoggingHandler faz a ponte: todo logging.info(...) do Python vira um log OTel.
    # Os campos passados em extra={...} viram atributos do log (filtráveis no Loki),
    # e o trace_id/span_id do request atual é anexado automaticamente.
    handler_otel = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    # O access log do werkzeug ("GET / 200") só repete o que o trace já mostra: fica só no console.
    handler_otel.addFilter(lambda registro: registro.name != "werkzeug")
    handler_console = logging.StreamHandler()
    handler_console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(handler_otel)
    raiz.addHandler(handler_console)

    # ---------- AUTO-INSTRUMENTAÇÃO ----------
    # Flask: um span por request + métricas HTTP (duração, status, rota).
    FlaskInstrumentor().instrument_app(app)
    # sqlite3: um span filho para cada query executada.
    SQLite3Instrumentor().instrument()

    return trace.get_tracer("sgdi"), metrics.get_meter("sgdi")
