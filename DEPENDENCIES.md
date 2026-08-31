# Dependências reproduzíveis

O `pyproject.toml` declara os intervalos aceitos pelo produto. Os arquivos de lock registram as
versões transitivas exatas resolvidas com Python 3.13:

- `requirements.lock`: API e worker em produção.
- `requirements-dev.lock`: produção, testes, cobertura e análise estática.
- `requirements.txt`: atalho compatível para instalar o lock de desenvolvimento.

## Instalação local

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Atualização controlada

Atualizações devem acontecer em uma alteração separada, seguidas pela suíte completa e build Docker:

```powershell
.\.venv\Scripts\python.exe -m piptools compile pyproject.toml --output-file requirements.lock --strip-extras --resolver backtracking
.\.venv\Scripts\python.exe -m piptools compile pyproject.toml --extra dev --output-file requirements-dev.lock --strip-extras --resolver backtracking
```

Os hashes de distribuição não foram incluídos porque a conexão local não concluiu o download de
artefatos de todas as plataformas. As versões estão travadas; hashes deverão ser acrescentados no
CI quando houver uma conexão estável para essa operação.

## Integração contínua

O workflow `.github/workflows/ci.yml` usa Python 3.13 e PostgreSQL 17 para validar, sem acessar
serviços pagos:

1. compatibilidade das dependências travadas com `pip check`;
2. análise estática com `ruff check .`;
3. aplicação e consistência das migrações com Alembic;
4. suíte automatizada com `pytest -q`.

Ele é acionado em alterações na branch `main`, pull requests destinados a ela e também pode ser
iniciado manualmente. As credenciais declaradas no workflow existem apenas durante o CI.
