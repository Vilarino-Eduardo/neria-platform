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

O avaliador executa três chamadas pagas, com no máximo 300 tokens de saída por chamada. Sem a
confirmação explícita, ele encerra antes de acessar a OpenAI:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_ai.py
.\.venv\Scripts\python.exe scripts\evaluate_ai.py --confirm-paid-api
```

Use a segunda forma somente em homologações autorizadas. A execução informa chamadas, tokens,
latência e aprovação de cada cenário, sem exibir a chave da API.

Para validar uma única resposta pelo pipeline completo — recuperação de conhecimento, cota,
persistência e fila de saída — sem enviar nada à Meta:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_ai_pipeline.py
.\.venv\Scripts\python.exe scripts\evaluate_ai_pipeline.py --confirm-paid-api
```

A empresa e os dados usados nessa prova são temporários e removidos ao final, inclusive em caso de
falha.
