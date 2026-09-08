# Checklist do piloto controlado

Este documento define quando a Neria estará pronta para receber as primeiras empresas reais. Itens de nuvem devem ser executados apenas quando houver data e participante definidos para o piloto.

## Bloqueadores antes da homologação

- [x] Cadastro, login, recuperação de senha e isolamento multiempresa.
- [x] Perfis de administrador e atendente, com limite inicial de três usuários.
- [x] Contatos, caixa de entrada, mensagens, fila, prioridade, etiquetas e histórico.
- [x] Webhook assinado da Meta, idempotência e envio assíncrono.
- [x] Automação configurável, base de conhecimento e IA com transferência humana.
- [x] Auditoria, retenção LGPD, exportação e anonimização.
- [x] Health checks, logs estruturados, migrações, Docker e testes de carga locais.
- [x] Jornada crítica local aprovada manualmente em desktop e celular.
- [ ] Estados de erro e indisponibilidade aprovados nas telas críticas (armazenamento pendente).
- [ ] Ambiente de homologação provisionado com domínio HTTPS.
- [ ] R2, PostgreSQL, Redis e rotina de backup configurados e validados.
- [ ] Número real da Meta conectado; recebimento, envio, status e templates validados.

Validação registrada em `LOCAL_ACCEPTANCE_2026-09-04.md`: as jornadas funcionais em desktop e
celular foram aprovadas localmente. As recuperações de indisponibilidade e as fronteiras externas
continuam pendentes, sem serem confundidas com a aprovação local.

## Homologações locais sem custo concluídas

- [x] Webhooks e status da Meta simulados pelo endpoint real, incluindo duplicidade.
- [x] Roteamento da IA simulado sem chamada externa ou reserva de cota.
- [x] Contrato S3 validado no MinIO com gravação, leitura e remoção.
- [x] E-mail transacional capturado e conferido no Mailpit.
- [x] Backup restaurado em banco temporário e comparado em todas as tabelas.
- [x] Queda temporária da Meta preserva a mensagem e permite reenvio sem duplicação.
- [x] Queda temporária do Redis preserva a mensagem pendente para recuperação periódica.
- [x] Queda real do PostgreSQL mantém liveness, sinaliza 503 com segurança e recupera readiness.
- [x] Código, migrations, API, worker e beat sincronizados na imagem local atual.
- [x] Suíte atual com 101 testes, dependências, segredos e análise estática aprovados.

As fronteiras entre simulação e validação real estão em `EXTERNAL_DEPENDENCIES.md`.

## Jornada de aceitação

1. Cadastrar uma nova empresa e entrar como administrador.
2. Completar perfil, horários, SLA e política de retenção.
3. Adicionar um atendente e confirmar o limite de três usuários.
4. Criar uma fonte de conhecimento e uma automação ativa.
5. Configurar a IA, simular uma pergunta conhecida e outra incerta.
6. Receber uma mensagem real pelo WhatsApp e confirmar que não há duplicação.
7. Transferir a conversa ao humano, atribuir, etiquetar e responder.
8. Encerrar o atendimento e validar dashboard, histórico e exportações.
9. Verificar a mesma jornada em largura de tela móvel.
10. Simular indisponibilidade da Meta e confirmar recuperação sem perda de mensagem.

## Critérios de aprovação

- Nenhuma empresa consegue consultar ou alterar dados de outra.
- Nenhuma mensagem recebida é processada duas vezes.
- Falhas temporárias não eliminam mensagens nem deixam a interface sem orientação.
- A IA não inventa uma resposta quando a confiança é insuficiente.
- A transferência humana preserva contexto e responsável.
- A jornada principal é utilizável em desktop e celular sem bloqueios.
- Testes automatizados e migrações passam antes de cada publicação.
- Backup e restauração são demonstrados antes de dados reais permanecerem no sistema.

## Evidências a registrar

- Data, versão e responsável pela validação.
- Empresa e número utilizados no teste.
- Capturas das etapas críticas e IDs das mensagens da Meta.
- Resultado dos testes automatizados e da restauração de backup.
- Problemas encontrados, severidade, decisão e versão da correção.

## Evidências disponíveis

- `LOCAL_ACCEPTANCE_2026-09-04.md`: homologação funcional local, limites e pendências.
- `PROJECT_PLAN.md`: gate técnico e roadmap atualizados em 08/09/2026.
