# Operação e resposta a incidentes

## Processos obrigatórios

A operação possui dois processos da aplicação usando a mesma versão:

- API web: recebe painel e webhooks.
- Worker Celery: envia mensagens e executa respostas da IA.

PostgreSQL e Redis devem estar saudáveis antes de iniciar os processos. A API expõe:

- `/api/v1/health/live`: processo ativo.
- `/api/v1/health/ready`: PostgreSQL e Redis disponíveis.

## Garantias da fila

- A tarefa somente é confirmada após terminar.
- Se o worker for perdido, a tarefa volta à fila.
- Cada worker reserva apenas uma tarefa por vez.
- Envio ao WhatsApp possui até quatro repetições com espera progressiva.
- Execuções pendentes da IA podem ser retomadas sem criar uma segunda resposta.
- O agendador reenvia execuções ainda pendentes. Uma execução em processamento por mais de cinco
  minutos é encerrada com `worker_interrupted`, libera a reserva de tokens e transfere a conversa
  para atendimento humano, sem repetir a chamada ao provedor.
- Falhas da IA registram apenas códigos seguros (`provider_timeout`,
  `provider_unavailable`, `provider_rate_limited`, `provider_quota_exhausted`,
  `provider_authentication_failed`, `provider_request_rejected`, `provider_http_error` ou
  `provider_error`), nunca a mensagem bruta recebida do provedor.
- Antes de qualquer chamada à OpenAI, a Neria mascara CPF formatado, números de cartão válidos,
  CVV e credenciais explicitamente rotuladas. A conversa original permanece no banco para o
  atendimento; somente a cópia enviada ao provedor é alterada. Essa barreira reduz exposição, mas
  não substitui a orientação ao cliente para não enviar dados sensíveis pelo WhatsApp.
- Webhooks falhos são reprocessados quando a Meta os repete.

## Mensagem não enviada

Após esgotar as tentativas automáticas:

1. A mensagem fica com status `failed`.
2. A causa e o número de tentativas permanecem registrados.
3. O contador da caixa de entrada passa a exigir atenção.
4. O operador abre a conversa e usa **Tentar novamente**.
5. O pedido de reenvio entra no histórico da conversa.

Antes de reenviar em massa, confirme se a conta do WhatsApp está ativa e se a Meta não apresenta indisponibilidade.

## Webhook falho

Um evento recebido é armazenado antes do processamento. Se ocorrer uma falha, ele recebe status `failed`. A repetição assinada da Meta reutiliza o mesmo evento e inicia novo processamento; eventos concluídos continuam sendo tratados como duplicados.

## Incidente: API indisponível

1. Consultar o health check de prontidão.
2. Se PostgreSQL ou Redis falhar, restaurar a dependência antes de reiniciar a API.
3. Consultar logs pelo `request_id` apresentado ao usuário.
4. Confirmar que web e worker usam a mesma versão e variáveis.
5. Depois da recuperação, verificar mensagens falhas e eventos pendentes.

## Incidente: worker parado

1. Reiniciar o worker sem limpar o Redis.
2. Confirmar conexão ao broker e registro das tarefas `whatsapp.send_message` e `ai.generate_reply`.
3. Aguardar a retomada automática das tarefas não confirmadas.
4. Conferir mensagens falhas na interface.

## Incidente: Meta indisponível

1. Não reenviar manualmente enquanto as tentativas automáticas estiverem ocorrendo.
2. Manter conversas e mensagens no banco; não excluir a fila.
3. Após normalização, reenviar somente itens que terminaram como `failed`.
4. Registrar início, fim, impacto e mensagens recuperadas.

## Publicação

1. Executar testes, análise estática e `alembic check`.
2. Fazer backup antes de migração com alteração de dados.
3. Aplicar `alembic upgrade head` uma única vez.
4. Publicar API e worker com a mesma imagem.
5. Validar readiness, login, webhook e uma mensagem de teste.

## Backup e restauração

O dump lógico deve ser criado antes de migrations destrutivas e periodicamente fora do provedor.
Um backup só é considerado válido depois de restaurado em outro banco e conferido.

Para homologar o procedimento localmente sem tocar no banco principal:

```powershell
.\.venv\Scripts\python.exe scripts\verify_backup_restore.py
```

O comando cria um dump em `backups/`, restaura em um banco temporário de nome restrito, compara a
migration e a contagem de todas as tabelas e remove somente esse banco temporário. Os arquivos de
backup podem conter dados pessoais e não devem ser versionados nem compartilhados sem proteção.

## Evidências mínimas de incidente

- Horário e duração.
- Serviço ou empresa afetada.
- IDs de requisição, conversa e mensagem, sem copiar conteúdo pessoal desnecessário.
- Causa, ação de recuperação e quantidade de mensagens reenviadas.
- Medida preventiva e responsável.
