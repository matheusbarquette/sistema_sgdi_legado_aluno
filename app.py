from flask import Flask, render_template, request, redirect, url_for, flash
import logging
import sqlite3
from datetime import datetime

from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.metrics import Observation

from telemetry import configurar_telemetria

app = Flask(__name__)
app.secret_key = '123456'

# ---------------------------------------------------------------------------
# Observabilidade (OpenTelemetry)
# ---------------------------------------------------------------------------
tracer, meter = configurar_telemetria(app)
logger = logging.getLogger('sgdi')

# Com debug=True o Flask deixa a exceção "vazar" para o debugger do Werkzeug e a
# instrumentação não chega a registrar o 500. Assim o Flask responde 500 normalmente:
# o erro entra na métrica HTTP, o span fica com status=error e o traceback vai pro Loki.
app.config['PROPAGATE_EXCEPTIONS'] = False

# Métricas de negócio (as de HTTP o FlaskInstrumentor já gera sozinho)
demandas_criadas = meter.create_counter(
    'sgdi.demandas.criadas', unit='1', description='Demandas criadas')
demandas_deletadas = meter.create_counter(
    'sgdi.demandas.deletadas', unit='1', description='Demandas deletadas')
comentarios_criados = meter.create_counter(
    'sgdi.comentarios.criados', unit='1', description='Comentários adicionados')
buscas_realizadas = meter.create_counter(
    'sgdi.buscas', unit='1', description='Buscas realizadas')
resultados_busca = meter.create_histogram(
    'sgdi.busca.resultados', unit='1', description='Quantidade de resultados por busca')

# Começa os counters em zero: sem isso o Prometheus só "enxerga" o counter depois do
# primeiro evento, e o increase() do dashboard perde esse primeiro incremento.
for contador in (demandas_criadas, demandas_deletadas, comentarios_criados):
    contador.add(0)
buscas_realizadas.add(0, {'com_resultado': True})
buscas_realizadas.add(0, {'com_resultado': False})


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


# Gauges observáveis: o SDK chama a função a cada exportação (5s)
meter.create_observable_gauge(
    'sgdi.demandas.total', callbacks=[observar_estoque], description='Demandas cadastradas no banco')
meter.create_observable_gauge(
    'sgdi.comentarios.orfaos', callbacks=[observar_comentarios_orfaos],
    description='Comentários ligados a demandas que não existem')


def get_db():
    conn = sqlite3.connect('demandas.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()
    demandas = cursor.execute('SELECT * FROM demandas').fetchall()
    conn.close()
    return render_template('index.html', demandas=demandas)


@app.route('/nova_demanda', methods=['GET', 'POST'])
def nova_demanda():
    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante = request.form['solicitante']


        # Span manual: aparece como filho do span do request no Tempo
        with tracer.start_as_current_span('salvar_demanda') as span:
            span.set_attribute('demanda.titulo', titulo)
            span.set_attribute('demanda.solicitante', solicitante)

            conn = sqlite3.connect('demandas.db')
            cursor = conn.cursor()

            cursor.execute(
                f"INSERT INTO demandas (titulo, descricao, solicitante, data_criacao) VALUES ('{titulo}', '{descricao}', '{solicitante}', '{datetime.now()}')")
            conn.commit()
            conn.close()

        demandas_criadas.add(1)
        logger.info('Demanda criada', extra={
            'evento': 'demanda_criada',
            'demanda_titulo': titulo,
            'solicitante': solicitante,
        })

        flash('Salvo!')
        return redirect('/')

    return render_template('nova_demanda.html')


@app.route('/editar/<id>', methods=['GET', 'POST'])
def editar(id):
    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form['descricao']
        solicitante = request.form['solicitante']

        cursor.execute(
            f"UPDATE demandas SET titulo='{titulo}', descricao='{descricao}', solicitante='{solicitante}' WHERE id={id}")
        conn.commit()
        conn.close()
        logger.info('Demanda editada', extra={'evento': 'demanda_editada', 'demanda_id': id})
        return redirect('/')

    demanda = cursor.execute(f'SELECT * FROM demandas WHERE id={id}').fetchone()
    conn.close()
    return render_template('editar.html', demanda=demanda)


@app.route('/deletar/<id>')
def deletar(id):
    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()
    cursor.execute(f'DELETE FROM demandas WHERE id={id}')
    removidas = cursor.rowcount
    conn.commit()
    conn.close()

    if removidas == 0:
        logger.warning('Tentativa de deletar demanda inexistente', extra={
            'evento': 'demanda_nao_encontrada', 'demanda_id': id})
    else:
        demandas_deletadas.add(removidas)
        logger.info('Demanda deletada', extra={'evento': 'demanda_deletada', 'demanda_id': id})

    flash('Deletado!')
    return redirect('/')


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

    buscas_realizadas.add(1, {'com_resultado': len(resultados) > 0})
    resultados_busca.record(len(resultados))
    logger.info('Busca realizada', extra={
        'evento': 'busca', 'termo': termo, 'quantidade_resultados': len(resultados)})
    return render_template('index.html', demandas=resultados)


# @app.route('/admin')
# def admin():
#     return 'Área administrativa'

@app.route('/detalhes/<id>')
def detalhes(id):
    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()
    demanda = cursor.execute(f'SELECT * FROM demandas WHERE id={id}').fetchone()

    comentarios = cursor.execute(f'SELECT * FROM comentarios WHERE demanda_id={id}').fetchall()
    conn.close()

    if demanda is None:
        logger.warning('Demanda não encontrada', extra={'evento': 'demanda_nao_encontrada', 'demanda_id': id})

    return render_template('detalhes.html', demanda=demanda, comentarios=comentarios)


@app.route('/adicionar_comentario/<demanda_id>', methods=['POST'])
def adicionar_comentario(demanda_id):
    comentario = request.form['comentario']
    autor = request.form['autor']

    conn = sqlite3.connect('demandas.db')
    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO comentarios (demanda_id, comentario, autor, data) VALUES ({demanda_id}, '{comentario}', '{autor}', '{datetime.now()}')")
    conn.commit()
    conn.close()

    comentarios_criados.add(1)
    logger.info('Comentário adicionado', extra={
        'evento': 'comentario_criado', 'demanda_id': demanda_id, 'autor': autor})

    return redirect(f'/detalhes/{demanda_id}')


def calcular_prazo(data_inicio):
    return "30 dias"


if __name__ == '__main__':
    # use_reloader=False: o reloader do modo debug sobe 2 processos e duplicaria a telemetria
    app.run(debug=True, host='0.0.0.0', use_reloader=False)