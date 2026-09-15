# Testes automatizados — cadastro de demandas


### 1. Teste Unitário

Testa uma **função isoladamente**.

```python
# calculadora.py
def somar(a, b):
    return a + b
```

```python
# test_calculadora.py
from calculadora import somar

def test_somar():
    assert somar(2, 3) == 5
```

**Serve para:** verificar se uma pequena parte do código funciona corretamente.

---

### 2. Teste de Integração

Testa se **partes diferentes do sistema funcionam juntas**.

```python
def test_criar_usuario(client):
    response = client.post("/users", json={
        "nome": "Maria"
    })

    assert response.status_code == 201
```

Aqui podemos estar testando:

```
API → Service → Banco de Dados
```

**Serve para:** verificar a comunicação entre componentes.

---

### 3. Teste E2E — End-to-End

Testa o **fluxo completo da aplicação**, simulando um usuário.

```python
def test_cadastro(page):
    page.goto("http://localhost:8000")

    page.fill("#nome", "Maria")
    page.click("#cadastrar")

    assert page.get_by_text("Cadastro realizado").is_visible()
```

Nesse caso, podemos usar **pytest + Playwright**.

O teste passa por:

```
Navegador → Frontend → API → Banco de Dados
```

**Serve para:** verificar se o sistema completo funciona como esperado.

**Resumindo:**  
**Unitário → função**  
**Integração → componentes juntos**  
**E2E → aplicação completa**

## Os 3 tipos

| | Testa | Usa Flask? | Usa banco real? | Usa navegador? | Velocidade |
|---|---|---|---|---|---|
| **Unitário** | 1 função isolada (`criar_demanda`) | ❌ | ❌ (mock) | ❌ | ⚡ milissegundos |
| **Integração** | rota + banco funcionando juntos | ✅ (test client) | ✅ (SQLite temporário) | ❌ | 🚗 rápido |
| **E2E** | o sistema inteiro, como o usuário usa | ✅ (servidor de verdade) | ✅ | ✅ (Chrome headless) | 🐢 mais lento |

Quanto mais alto na pirâmide de testes (unitário → integração → E2E), mais
"real" o teste é, mas também mais lento e mais frágil. Por isso a regra
prática é: **muitos testes unitários, um número médio de testes de
integração, e só alguns poucos E2E** nos fluxos mais importantes.

---

## 1. Teste Unitário

📄 [`tests/unit/test_criar_demanda_unit.py`](tests/unit/test_criar_demanda_unit.py)

Testa **só a função `criar_demanda()`**, sozinha, sem subir o Flask e sem
tocar em nenhum arquivo `.db`. A conexão com o banco é substituída por um
dublê (`unittest.mock.MagicMock`) — o teste não sabe nem se importa se por
trás existe SQLite, Postgres ou nada.

```python
def test_criar_demanda_retorna_o_id_gerado_pelo_banco():
    conn = MagicMock()
    conn.cursor.return_value.lastrowid = 42

    novo_id = criar_demanda(conn, 'Corrigir tela de login', 'Descrição', 'Maria')

    assert novo_id == 42
    assert novo_id is not None
```

**Quando usar:** para testar regras de negócio e lógica pura, com o maior
número de casos possível (também o mais barato de manter). É o primeiro
lugar onde um bug como o do `id None` poderia ter sido pego — se
existisse antes da correção.

**Como rodar:**
```bash
pytest tests/unit -v
```

---

## 2. Teste de Integração

📄 [`tests/integration/test_cadastro_integration.py`](tests/integration/test_cadastro_integration.py)
📄 [`tests/integration/conftest.py`](tests/integration/conftest.py) *(cria um banco SQLite temporário a cada teste)*

Testa a rota `/nova_demanda` **de verdade**, usando o `test_client()` do
Flask (que simula requisições HTTP sem precisar subir um servidor), mais um
banco SQLite real — só que temporário, criado do zero antes de cada teste e
descartado depois. Não usa mock: se o SQL estiver errado, o teste quebra de
verdade.

```python
def test_post_nova_demanda_persiste_no_banco_com_id_valido(client):
    response = client.post('/nova_demanda', data={
        'titulo': 'Corrigir bug no cadastro',
        'descricao': 'A demanda estava sendo salva com id None',
        'solicitante': 'Professor',
    })

    conn = sqlite3.connect('demandas.db')
    linha = conn.execute(
        "SELECT id, titulo FROM demandas WHERE titulo = ?",
        ('Corrigir bug no cadastro',)
    ).fetchone()

    assert linha is not None
    assert linha[0] is not None   # é exatamente o bug que motivou este teste
```

**Quando usar:** para garantir que as peças (rota + banco + template) se
encaixam. É o nível onde o bug do `id None` foi comprovado de fato (o valor
`None` só aparece quando a inserção realmente acontece no banco).

**Como rodar:**
```bash
pytest tests/integration -v
```

---

## 3. Teste E2E (End-to-End)

📄 [`tests/e2e/test_cadastro_e2e.py`](tests/e2e/test_cadastro_e2e.py)
📄 [`tests/e2e/conftest.py`](tests/e2e/conftest.py) *(sobe o Flask de verdade numa porta + abre o Chrome headless)*

Abre um **navegador Chrome de verdade** (em modo *headless*, sem
interface visível) contra o servidor Flask rodando numa porta real, e faz
exatamente o que um usuário faria: abre a página, preenche os campos, clica
em "Salvar" e confere o resultado na tela.

```python
def test_usuario_cadastra_demanda_pela_interface(servidor_url, navegador):
    navegador.get(f'{servidor_url}/nova_demanda')

    navegador.find_element(By.NAME, 'titulo').send_keys('Demanda criada via E2E')
    navegador.find_element(By.NAME, 'descricao').send_keys('Criada pelo Selenium')
    navegador.find_element(By.NAME, 'solicitante').send_keys('Robô de Teste')
    navegador.find_element(By.CSS_SELECTOR, 'form[action="/nova_demanda"] button[type="submit"]').click()

    WebDriverWait(navegador, 5).until(EC.url_to_be(f'{servidor_url}/'))

    primeira_coluna = linha_nova[0].find_elements(By.TAG_NAME, 'td')[0]
    assert primeira_coluna.text.strip().isdigit()   # tem um ID de verdade na tela, não "None"
```

**Quando usar:** com moderação, só nos fluxos mais críticos do sistema
(aqui, cadastrar uma demanda). É o teste que mais se parece com o usuário
final, mas também o mais lento e o mais sensível a mudanças de layout —
por isso não vale a pena escrever um E2E para cada telinha do sistema.

**Como rodar:**
```bash
pytest tests/e2e -v
```
*(precisa do Google Chrome instalado; o Selenium baixa o driver
automaticamente na primeira execução.)*

---

## Rodando tudo

```bash
pip install -r requirements-dev.txt
pytest
```

```
tests/
├── unit/          -> não usa Flask nem banco (mock)
├── integration/   -> Flask + SQLite reais, banco temporário e descartável
└── e2e/           -> servidor Flask real + Chrome headless real
```

Os testes de integração e E2E sempre criam um `demandas.db` **temporário**
(em outra pasta) — o banco real do projeto nunca é tocado pelos testes.
