"""
Gera tráfego no SGDI para popular o dashboard durante a aula.

Uso:  python gerar_trafego.py            (roda até Ctrl+C)
      python gerar_trafego.py 200        (faz 200 iterações e para)

Mistura acessos normais, buscas com e sem resultado, criação de demandas,
comentários e alguns erros de propósito (404 de negócio e 500 do SQL legado).
"""
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# 127.0.0.1 em vez de localhost: no Windows o localhost tenta IPv6 antes e cada request leva ~2s
BASE = 'http://127.0.0.1:5000'
TERMOS = ['bug', 'relatório', 'performance', 'filtros', 'login', 'xpto', 'café']


def chamar(caminho, dados=None):
    corpo = urllib.parse.urlencode(dados).encode() if dados else None
    try:
        with urllib.request.urlopen(BASE + caminho, data=corpo, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as erro:
        return erro.code


def uma_rodada(i):
    acoes = [
        (40, lambda: chamar('/')),
        (25, lambda: chamar('/buscar?q=' + urllib.parse.quote(random.choice(TERMOS)))),
        (15, lambda: chamar(f'/detalhes/{random.choice([1, 2, 3, 5, 42])}')),
        (8, lambda: chamar('/nova_demanda', {
            'titulo': f'Demanda gerada {i}', 'descricao': 'Criada pelo gerador de tráfego',
            'solicitante': random.choice(['Ana', 'Bruno', 'Carla'])})),
        (7, lambda: chamar('/adicionar_comentario/2', {'comentario': 'Alguma novidade?', 'autor': 'Aluno'})),
        (3, lambda: chamar(f'/deletar/{random.randint(100, 999)}')),
        (2, lambda: chamar('/editar/abc')),  # id não numérico -> SQL quebra -> 500
    ]
    pesos = [peso for peso, _ in acoes]
    _, acao = random.choices(acoes, weights=pesos)[0]
    return acao()


if __name__ == '__main__':
    total = int(sys.argv[1]) if len(sys.argv) > 1 else None
    i = 0
    print(f'Gerando tráfego em {BASE} (Ctrl+C para parar)...')
    try:
        while total is None or i < total:
            status = uma_rodada(i)
            i += 1
            print(f'\r{i} requisições (última: {status})', end='', flush=True)
            time.sleep(random.uniform(0.05, 0.4))
    except KeyboardInterrupt:
        pass
    print()
