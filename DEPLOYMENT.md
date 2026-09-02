# Implantação da Neria

## Arquitetura do piloto

- Railway: API web, worker Celery, PostgreSQL e Redis.
- Cloudflare R2: documentos privados da base de conhecimento.
- Cloudflare DNS: domínio e HTTPS na frente do endereço público da API.

## Serviços no Railway

Crie um projeto com PostgreSQL e Redis e conecte duas instâncias deste repositório:

1. **neria-web**
   - Start command: deixe o `CMD` do Dockerfile.
   - Pre-deploy command: `alembic upgrade head`.
   - Healthcheck: `/api/v1/health/ready`.
2. **neria-worker**
   - Start command: `celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO`.
   - Sem domínio público e sem healthcheck HTTP.

O Railway detecta automaticamente o `Dockerfile`. Não utilize `railway.toml`: o formato está
descontinuado para novos serviços.

## Variáveis obrigatórias

Configure nos dois serviços:

- `ENVIRONMENT=production`
- `DEBUG=false`
- `DATABASE_URL` referenciando o PostgreSQL; use o formato `postgresql+psycopg://...`.
- `REDIS_URL` referenciando o Redis.
- `SECRET_KEY` aleatória com pelo menos 32 caracteres.
- `CREDENTIAL_ENCRYPTION_KEY` no formato Fernet, gerada exclusivamente para a aplicação.
- `META_APP_SECRET` com pelo menos 32 caracteres e `META_WEBHOOK_VERIFY_TOKEN` com pelo menos 24.
- `OBJECT_STORAGE_BACKEND=r2`.
- `R2_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
- `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` e `R2_BUCKET_NAME`.
- `SMTP_HOST`, `SMTP_USE_TLS=true` e as credenciais SMTP exigidas pelo provedor.
- `PASSWORD_RESET_URL` em HTTPS, usando o domínio público e contendo `{token}`.
- `REGISTRATION_IP_LIMIT=20` e `REGISTRATION_RATE_WINDOW_SECONDS=3600` limitam cadastros públicos por IP.
- `OPENAI_API_KEY` quando a IA real for ativada.

O token do R2 deve ter leitura e escrita somente no bucket da Neria. O bucket permanece privado.
As rotas `/docs`, `/redoc` e `/openapi.json` são desativadas automaticamente em produção.
Defina `TRUSTED_PROXY_NETWORKS` com os IPs ou CIDRs dos proxies que podem enviar `X-Forwarded-For`.
Não use `0.0.0.0/0`: conexões fora dessas redes ignoram o cabeçalho para impedir falsificação do IP.
Se o Redis ficar indisponível, cada instância aplica temporariamente os limites em memória.
Essa contingência reduz abuso durante falhas, mas não substitui o Redis no controle distribuído.
A interface usa cookie de sessão `HttpOnly`, `SameSite=Lax` e `Secure` automaticamente em produção.
Operações autenticadas por cookie também exigem um token CSRF correspondente no cabeçalho.
Novas senhas exigem 12 a 128 caracteres e padrões comuns ou repetitivos são recusados localmente.
Conflitos simultâneos no cadastro público são revertidos e retornam `409`, sem deixar transações quebradas.
O mesmo tratamento centralizado protege a criação de usuários e contatos duplicados.
Falhas transitórias do banco retornam `503` e `Retry-After`, configurável por `DATABASE_RETRY_AFTER_SECONDS`.
No encerramento da API, o pool do banco e a conexão Redis são liberados de forma controlada.
Requisições acima de `MAX_REQUEST_BODY_BYTES` (12 MB por padrão) são recusadas com `413`.
Valores de exemplo como `change-this`, `development` ou `example` são recusados quando
`ENVIRONMENT=production`; a aplicação não inicia com configuração incompleta ou insegura.

## Backups

Ative no PostgreSQL do Railway:

- snapshot diário;
- snapshot semanal;
- recuperação point-in-time quando o plano escolhido disponibilizar;
- dump lógico externo periódico e teste de restauração.

Antes do piloto, faça ao menos um teste completo de restauração em outro banco.

## Liberação

1. Executar `pytest` e `alembic check`.
2. Implantar primeiro em um ambiente de homologação.
3. Validar `/api/v1/health/ready`.
4. Configurar o webhook da Meta no domínio público.
5. Realizar envio e recebimento reais com um número de teste.

Os procedimentos de falha, reenvio e incidentes estão em `OPERATIONS.md`.
