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

## Evidências técnicas

- Mensagem simulada final: `wamid.local.d940e6908cf543cf94d86163b55cbf95`.
- Rede externa utilizada pelo simulador: `false`.
- Suíte automatizada: 92 testes aprovados.
- Ruff: aprovado.
- Alembic: nenhuma operação de migração pendente.
- Verificação de diferenças e busca de segredos versionados: aprovadas.
- Correção registrada no commit `d9d7f2e`.

## Limites desta aprovação

Esta execução não aprova a jornada real de produção. Permanecem pendentes:

- repetir toda a jornada funcional em largura móvel;
- ampliar os testes manuais de indisponibilidade e recuperação;
- provisionar homologação pública com HTTPS, banco, Redis, R2 e backups;
- conectar número real da Meta e validar recebimento, envio, status e templates;
- validar o provedor de IA real com orçamento e critérios de qualidade controlados.

O onboarding permaneceu em 75% de propósito: a quarta etapa exige verificação real das credenciais da Meta e não deve ser simulada como concluída.
