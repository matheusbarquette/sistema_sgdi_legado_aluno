"""
TESTE UNITÁRIO - cadastro de demandas
======================================

O que é: testa UMA função isolada, sem Flask, sem banco de dados de verdade
e sem rede. Tudo que a função `criar_demanda` precisa (a conexão com o banco)
é substituído por um "dublê" (Mock). É o teste mais rápido e mais barato de
rodar, por isso deve ser o mais numeroso.

O que este arquivo garante:
- `criar_demanda` monta o INSERT corretamente e usa parâmetros (?, ?, ?, ?)
  em vez de concatenar texto (o que evitaria SQL Injection).
- `criar_demanda` chama `conn.commit()`.
- `criar_demanda` devolve o id gerado pelo banco (`cursor.lastrowid`),
  nunca `None`.
"""
from unittest.mock import MagicMock

from app import criar_demanda


def test_criar_demanda_retorna_o_id_gerado_pelo_banco():
    conn = MagicMock()
    conn.cursor.return_value.lastrowid = 42

    novo_id = criar_demanda(conn, 'Corrigir tela de login', 'Descrição', 'Maria')

    assert novo_id == 42
    assert novo_id is not None


def test_criar_demanda_usa_query_parametrizada_sem_concatenar_texto():
    conn = MagicMock()
    cursor = conn.cursor.return_value

    criar_demanda(conn, 'Título', 'Descrição', 'Solicitante')

    sql, params = cursor.execute.call_args[0]
    assert '?' in sql
    assert 'Título' not in sql          # não foi colado direto na string
    assert params[0] == 'Título'
    assert params[1] == 'Descrição'
    assert params[2] == 'Solicitante'


def test_criar_demanda_faz_commit_para_persistir_a_demanda():
    conn = MagicMock()

    criar_demanda(conn, 'Título', 'Descrição', 'Solicitante')

    conn.commit.assert_called_once()
