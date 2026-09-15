import socket
import sqlite3
import threading
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


SCHEMA = '''
CREATE TABLE demandas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT,
    descricao TEXT,
    solicitante TEXT,
    data_criacao TEXT
);
CREATE TABLE comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demanda_id INTEGER,
    comentario TEXT,
    autor TEXT,
    data TEXT
);
'''


def _porta_livre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _esperar_servidor(url, tentativas=40):
    for _ in range(tentativas):
        try:
            with socket.create_connection(('127.0.0.1', url), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError('servidor Flask não respondeu a tempo')


@pytest.fixture(scope='module')
def servidor_url(tmp_path_factory, monkeypatch_module):
    """Sobe a aplicação Flask REAL (com Werkzeug) num banco temporário,
    igual rodaria em produção, para o navegador de verdade acessar.
    """
    tmp_path = tmp_path_factory.mktemp('e2e_db')
    monkeypatch_module.chdir(tmp_path)

    conn = sqlite3.connect(tmp_path / 'demandas.db')
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

    import app as app_module
    porta = _porta_livre()

    thread = threading.Thread(
        target=app_module.app.run,
        kwargs={'host': '127.0.0.1', 'port': porta, 'use_reloader': False, 'debug': False},
        daemon=True,
    )
    thread.start()
    _esperar_servidor(porta)

    yield f'http://127.0.0.1:{porta}'


@pytest.fixture(scope='module')
def monkeypatch_module():
    """monkeypatch padrão do pytest é function-scoped; aqui precisamos de
    escopo de módulo para não derrubar o servidor entre os testes."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope='module')
def navegador():
    opts = Options()
    # opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1280,800')
    driver = webdriver.Chrome(options=opts)
    yield driver
    driver.quit()
