# Homologação local — 04/09/2026

## Escopo desta execução

- Ambiente Docker local com API, PostgreSQL, Redis e worker.
- Empresa isolada de homologação: `b7719ac1-b557-4195-aada-2af9301ca07b`.
- Conta fictícia do WhatsApp: `qa-phone-20260904` / `qa-business-20260904`.
- Webhook assinado enviado pelo simulador, sem acesso à rede externa.
- Interface web validada manualmente em navegador.

Nenhuma credencial, senha ou token foi registrado neste documento.

## Resultados aprovados

1. Cadastro e sessão administrativa estavam operacionais.
2. Perfil comercial, endereço, descrição e horários foram salvos.
3. Fonte manual de conhecimento foi criada e processada.
4. Automação de atendimento foi criada, definida como fallback e ativada.
5. Conta fictícia do WhatsApp foi salva e permaneceu corretamente como não verificada.
6. Webhook local foi aceito e a duplicidade foi descartada.
7. A automação gerou resposta pelo mesmo pipeline usado pela integração.
8. O envio externo foi bloqueado por ausência de conta Meta verificada e apareceu como falha recuperável na interface.
9. Transferência humana, atribuição, prioridade e encerramento funcionaram.
10. O painel foi corrigido para limpar a conversa selecionada depois do encerramento.
11. A página principal passou a exigir revalidação de cache, evitando carregar uma versão antiga após publicação.
12. A interface não apresentou erros ou avisos no console durante a validação final.
13. A jornada funcional móvel foi repetida em 390 × 844 pixels.
14. Recebimento, abertura, transferência humana, resposta, prioridade, atribuição e encerramento funcionaram na largura móvel.
15. Os controles de prioridade e responsável, antes ocultos no celular, foram reposicionados em uma faixa horizontal acessível.
16. Uma indisponibilidade temporária da Meta foi simulada no cliente de produção: a mensagem permaneceu armazenada, foi exposta como falha recuperável e, após o reenvio, mudou para enviada sem duplicação.
17. Uma indisponibilidade temporária do Redis/fila foi simulada: a API preservou a mensagem como pendente e o recuperador periódico a reenfileirou quando o broker voltou.
18. O PostgreSQL local foi desligado de fato: liveness permaneceu em 200, readiness identificou somente o banco como indisponível e operações dependentes responderam 503 com orientação segura, `Retry-After` e código de suporte.
19. Após religar o PostgreSQL, o contêiner voltou a saudável e readiness retornou 200 com banco e Redis operacionais.

## Evidências técnicas

- Mensagem simulada final: `wamid.local.d940e6908cf543cf94d86163b55cbf95`.
- Mensagem usada na jornada móvel: `wamid.local.93259a569ff44d199396b1b6ebc7146d`.
- Rede externa utilizada pelo simulador: `false`.
- Suíte automatizada: 94 testes aprovados.
- Ruff: aprovado.
- Alembic: nenhuma operação de migração pendente.
- Verificação de diferenças e busca de segredos versionados: aprovadas.
- Correção registrada no commit `d9d7f2e`.

## Limites desta aprovação

Esta execução não aprova a jornada real de produção. Permanecem pendentes:

- ampliar os testes de indisponibilidade para armazenamento e demais componentes externos;
- provisionar homologação pública com HTTPS, banco, Redis, R2 e backups;
- conectar número real da Meta e validar recebimento, envio, status e templates;
- validar o provedor de IA real com orçamento e critérios de qualidade controlados.

O onboarding permaneceu em 75% de propósito: a quarta etapa exige verificação real das credenciais da Meta e não deve ser simulada como concluída.

## Atualização técnica — 08/09/2026

- A conexão local do PostgreSQL foi fixada em IPv4 e recebeu timeout explícito de cinco segundos.
- O problema de permissão da pasta temporária global do Pytest foi isolado no próprio workspace.
- A suíte atual aprovou 101 testes em 44,79 segundos e o Ruff permaneceu aprovado.
- API, worker, beat e migrations foram reconstruídos com a mesma versão do código.
- A migration `a7f3c91d2e64` está aplicada e reconhecida pela imagem atual.
- A API retornou readiness com PostgreSQL e Redis operacionais, e o worker respondeu ao ping.
- A busca de conhecimento passou a realizar pré-seleção lexical indexada no PostgreSQL.

Esta atualização não altera os limites da homologação de 04/09: armazenamento indisponível,
serviços externos e operação com empresa real continuam pendentes.
