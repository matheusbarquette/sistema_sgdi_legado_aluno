"""
TESTE DE INTEGRAÇÃO - cadastro de demandas
============================================

O que é: testa várias peças reais trabalhando juntas - a rota Flask, o
parsing do formulário e o banco de dados SQLite de verdade (só que um banco
temporário, criado e destruído a cada teste). Não usa mocks. É mais lento
que o teste unitário, mas garante que as peças se encaixam.

O que este arquivo garante:
- POST em /nova_demanda realmente grava uma linha na tabela `demandas`.
- A linha gravada tem um id numérico válido (não None) - é exatamente o
  bug que motivou este README/testes.
- Os dados enviados no formulário chegam intactos no banco.
- Depois de cadastrar, a demanda aparece na listagem (`/`).
"""
import sqlite3


def test_post_nova_demanda_persiste_no_banco_com_id_valido(client):
    response = client.post('/nova_demanda', data={
        'titulo': 'Corrigir bug no cadastro',
        'descricao': 'A demanda estava sendo salva com id None',
        'solicitante': 'Professor',
    }, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'] in ('/', 'http://localhost/')

    conn = sqlite3.connect('demandas.db')
    linha = conn.execute(
        "SELECT id, titulo, descricao, solicitante FROM demandas WHERE titulo = ?",
        ('Corrigir bug no cadastro',)
    ).fetchone()
    conn.close()

    assert linha is not None, 'a demanda não foi encontrada no banco'
    id_gerado, titulo, descricao, solicitante = linha
    assert id_gerado is not None
    assert isinstance(id_gerado, int)
    assert titulo == 'Corrigir bug no cadastro'
    assert descricao == 'A demanda estava sendo salva com id None'
    assert solicitante == 'Professor'


def test_demanda_cadastrada_aparece_na_listagem(client):
    client.post('/nova_demanda', data={
        'titulo': 'Demanda visível na home',
        'descricao': 'Descrição qualquer',
        'solicitante': 'Aluno',
    })

    response = client.get('/')

    assert response.status_code == 200
    assert b'Demanda vis\xc3\xadvel na home' in response.data


def test_get_nova_demanda_exibe_formulario(client):
    response = client.get('/nova_demanda')

    assert response.status_code == 200
    assert b'<form' in response.data
    assert b'name="titulo"' in response.data
