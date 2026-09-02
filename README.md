# Execução completa com Docker

Para iniciar infraestrutura, migrações, API, worker e agendador:

```bash
docker compose --profile app up --build
```

A interface fica disponível em `http://localhost:8000/app`. Sem o perfil `app`, o Compose
continua iniciando apenas PostgreSQL, Redis, MinIO e Mailpit.

Antes de criar um commit, verifique se nenhum segredo entrou nos arquivos rastreados:

```bash
python scripts/check_secrets.py
```

## Avaliação controlada da IA real

O avaliador executa quatro chamadas pagas, com no máximo 300 tokens de saída por chamada. Sem a
confirmação explícita, ele encerra antes de acessar a OpenAI:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_ai.py
.\.venv\Scripts\python.exe scripts\evaluate_ai.py --confirm-paid-api
.\.venv\Scripts\python.exe scripts\evaluate_ai.py --scenario instrucao_maliciosa_na_fonte --confirm-paid-api
```

Use as formas pagas somente em homologações autorizadas. A última executa apenas um cenário. A execução informa chamadas, tokens,
latência e aprovação de cada cenário, sem exibir a chave da API.

Para validar uma única resposta pelo pipeline completo — recuperação de conhecimento, cota,
persistência e fila de saída — sem enviar nada à Meta:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_ai_pipeline.py
.\.venv\Scripts\python.exe scripts\evaluate_ai_pipeline.py --confirm-paid-api
```

A empresa e os dados usados nessa prova são temporários e removidos ao final, inclusive em caso de
falha.

O consumo real é protegido por dois limites diários por empresa: quantidade de chamadas e tokens.
O padrão inicial é 50 chamadas e 100.000 tokens; ambos podem ser reduzidos pela administração do
plano sem alterar o código.
