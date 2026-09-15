"""
TESTE E2E (End-to-End) - cadastro de demandas
================================================

O que é: o teste mais "de fora para dentro" que existe. Não chama nenhuma
função Python diretamente - ele abre um navegador de verdade (Chrome, aqui
em modo headless), clica e digita exatamente como um usuário faria, contra
o servidor Flask real rodando numa porta. É o mais lento e mais frágil dos
três, então deve ser usado com moderação - só nos fluxos mais importantes
(como o cadastro de demandas).

O que este arquivo garante:
- Um usuário consegue abrir "Nova Demanda", preencher o formulário e clicar
  em Salvar.
- Depois de salvar, ele é redirecionado para a Home e vê a demanda que
  acabou de criar na tabela - com um ID de verdade, não em branco/None.
"""
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def test_usuario_cadastra_demanda_pela_interface(servidor_url, navegador):
    # Abre a página do formulário
    navegador.get(f'{servidor_url}/nova_demanda')
    time.sleep(1)  # Pausa para visualizar a página recém-aberta

    # Preenche o campo 'titulo'
    navegador.find_element(By.NAME, 'titulo').send_keys('Demanda criada via E2E')
    time.sleep(0.5)  # Pausa visual após digitar o título

    # Preenche o campo 'descricao'
    navegador.find_element(By.NAME, 'descricao').send_keys('Criada pelo Selenium')
    time.sleep(0.5)  # Pausa visual após digitar a descrição

    # Preenche o campo 'solicitante'
    navegador.find_element(By.NAME, 'solicitante').send_keys('Robô de Teste')
    time.sleep(1)  # Pausa para visualizar o formulário totalmente preenchido

    # Clica no botão de enviar
    navegador.find_element(By.CSS_SELECTOR, 'form[action="/nova_demanda"] button[type="submit"]').click()

    # Espera o redirect terminar de verdade (evita teste "flaky")
    WebDriverWait(navegador, 5).until(
        EC.url_to_be(f'{servidor_url}/')
    )
    time.sleep(1.5)  # Pausa para observar a página inicial após o redirecionamento

    # Validação dos elementos na tabela
    linhas = navegador.find_elements(By.CSS_SELECTOR, 'table tbody tr')
    linha_nova = [l for l in linhas if 'Demanda criada via E2E' in l.text]
    assert linha_nova, 'a demanda cadastrada não apareceu na listagem'

    primeira_coluna = linha_nova[0].find_elements(By.TAG_NAME, 'td')[0]
    assert primeira_coluna.text.strip() != ''
    assert primeira_coluna.text.strip().lower() != 'none'
    assert primeira_coluna.text.strip().isdigit()
    
    time.sleep(1)  # Pausa final antes de fechar/encerrar o teste