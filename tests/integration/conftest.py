import sqlite3

import pytest


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


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Sobe a aplicação Flask real, mas apontada para um demandas.db
    temporário e vazio — assim o teste de integração exercita o
    app + o banco de verdade, sem sujar (nem depender d)o banco do projeto.
    """
    monkeypatch.chdir(tmp_path)
    conn = sqlite3.connect(tmp_path / 'demandas.db')
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

    import app as app_module
    app_module.app.config['TESTING'] = True

    with app_module.app.test_client() as test_client:
        yield test_client
