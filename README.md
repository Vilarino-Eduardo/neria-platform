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
