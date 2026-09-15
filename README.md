# SGDI - Sistema de Gestão de Demandas Internas

Sistema para gerenciar demandas internas da empresa.

## Como rodar

```bash
python init_db.py
python app.py
```

Acesse: http://localhost:5000

## Funcionalidades

- Criar demandas
- Editar demandas
- Deletar demandas
- Visualizar detalhes
- Comentários

## Testes

O projeto tem testes automatizados (unitário, integração e E2E) para o
cadastro de demandas. Veja **[TESTES.md](TESTES.md)** para a explicação de
cada tipo e como rodar.

```bash
pip install -r requirements-dev.txt
pytest
```

---

**TODO:**
- Adicionar prioridades
- Melhorar busca
- Adicionar usuários

---

*Desenvolvido em 2024*