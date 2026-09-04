# Neria — Diretrizes do Produto e Diagnóstico Inicial

## Objetivo

Construir uma plataforma SaaS multiempresa de atendimento pelo WhatsApp para comércios, prestadores de serviços e profissionais autônomos.

## Escopo definido para o MVP

- Integração oficial com a WhatsApp Cloud API da Meta.
- Uma conta isolada por empresa.
- Um número de WhatsApp por empresa no MVP.
- Modelo preparado para vários números no futuro.
- Até três usuários por empresa.
- Perfis iniciais: administrador e atendente.
- Atendimento humano dentro do painel.
- Transferência controlada entre bot e atendente.
- Editor simples de menus e respostas automáticas.
- IA baseada nas informações da empresa, documentos e histórico recente.
- Transferência para atendente quando a IA não souber responder.
- Base de conhecimento com PDF, DOCX, TXT e conteúdo digitado no painel.
- IA sem ações externas no MVP, mas preparada para ferramentas futuras.
- Planos e limites administrados manualmente no MVP.
- Estrutura preparada para cobrança automática futura.
- Aplicação em nuvem com PostgreSQL, armazenamento de arquivos e backups gerenciados.
- Interface responsiva, sem aplicativo móvel próprio no MVP.
- Português do Brasil, com estrutura preparada para internacionalização.

## Princípio de construção

Entregar cada função do MVP da maneira mais simples que seja confiável, mantendo contratos, dados e módulos preparados para evoluções previsíveis. Evitar soluções descartáveis e complexidade prematura.

## Diagnóstico do projeto atual

### Manter como conceito

- Separação entre rotas, serviços e repositórios.
- Clientes e configurações por cliente.
- Conversas e histórico.
- Sessões conversacionais.
- Tickets de atendimento.
- Documentos.
- Simulador web de chat para desenvolvimento.
- Menu, informações da empresa e transferência para atendimento como casos de uso.

### Adaptar

- Serviço de mensagens para trabalhar com eventos normalizados.
- Fluxo atual do bot para utilizar automações configuráveis.
- Sessões para considerar empresa, canal, número receptor e contato.
- Tickets para suportar fila, responsável, prioridade e histórico.
- Documentos para isolamento por empresa e processamento da base de conhecimento.
- Configurações para suportar limites e recursos por plano.
- Simulador para utilizar o mesmo pipeline empregado pelo WhatsApp.

### Substituir

- SQLite por PostgreSQL antes do início da operação real.
- Criação manual de tabelas por modelos e migrations versionadas.
- Conexão global com o banco por gerenciamento adequado de sessões.
- Identificação da empresa pelo telefone do remetente por identificação baseada no número receptor conectado.
- Envio simulado no terminal pela integração real com a Meta.
- Menus e estados codificados diretamente em `bot.py` por um motor configurável.
- Protocolos aleatórios curtos por identificadores seguros.
- Upload compartilhado por armazenamento isolado por empresa, com validação e limites.
- Painel administrativo ilustrativo por módulos funcionais e autenticados.

### Excluir ou arquivar após validação

- Implementações antigas baseadas em JSON.
- Catálogos e dados usados apenas nos primeiros testes.
- Arquivos de teste duplicados.
- Código sem uso depois que o comportamento necessário estiver documentado ou testado.
- Telas provisórias substituídas pelo painel definitivo.

Nenhuma exclusão deverá ocorrer antes de confirmar que o item não contém regra útil para o produto.

## Ordem de construção

1. Consolidar arquitetura, estrutura do projeto e modelo de dados.
2. Implementar autenticação, empresas, usuários, perfis e isolamento multiempresa.
3. Criar o núcleo de contatos, conversas, mensagens, sessões e tickets.
4. Integrar a WhatsApp Cloud API com webhooks, envio, status e idempotência.
5. Construir a caixa de entrada e a transferência para atendimento humano.
6. Criar o editor simples de menus e automações.
7. Construir upload, extração e indexação da base de conhecimento.
8. Integrar a IA com fontes, limites de confiança e transferência segura.
9. Completar configurações, relatórios essenciais e administração de planos.
10. Implementar segurança, LGPD, observabilidade, backups e testes de carga.
11. Realizar piloto controlado e preparar a operação comercial.

## Momento da IA

A interface do serviço de IA será definida durante a arquitetura para evitar acoplamento a um fornecedor. A IA funcional será construída depois que conversas, automações e base de conhecimento estiverem estáveis. Isso evita refazer prompts, memória, permissões e recuperação de documentos.

## Estado atual — 28/08/2026

As etapas 1 a 10 do roadmap técnico foram implementadas para o protótipo. O produto já possui arquitetura multiempresa, autenticação, equipe, contatos, atendimento humano, WhatsApp Cloud API, automações, base de conhecimento, IA com transferência segura, métricas, auditoria, LGPD, observabilidade, Docker e preparação para armazenamento R2.

A suíte automatizada, as migrações e a imagem Docker estão operacionais. A linha de base de desempenho local está documentada em `PERFORMANCE.md`. O provisionamento real de Railway, R2, domínio e backups foi adiado deliberadamente até a proximidade do piloto, evitando custo e configuração prematuros.

## Roadmap restante até a venda

### 1. Preparação do piloto — fase atual

- [x] Consolidar jornadas críticas em testes integrados de aceitação.
- [x] Criar dados demonstrativos reproduzíveis para apresentação e homologação.
- [x] Executar revisão funcional e responsiva das telas principais.
- [x] Tratar mensagens de erro, estados vazios e recuperação de falhas mais importantes.
- [x] Documentar operação, suporte e procedimento de incidentes do piloto.

### 2. Piloto controlado

- Provisionar ambiente de homologação e configurar domínio, R2 e backups.
- Conectar um número real da Meta e validar mensagens, status e templates.
- Operar com uma a três empresas selecionadas e acompanhar qualidade, custo e carga.
- Corrigir problemas encontrados sem ampliar desnecessariamente o escopo.

### 3. Preparação comercial

- Congelar o escopo da primeira oferta e definir preço, limites e termos.
- Finalizar identidade visual e textos comerciais.
- Criar landing page, demonstração guiada e materiais de onboarding.
- Implantar cobrança automática somente quando o processo manual estiver validado.

### 4. Lançamento profissional

- Realizar revisão final de segurança e privacidade.
- Validar restauração de backup e plano de continuidade.
- Definir indicadores de suporte, disponibilidade e uso da IA.
- Publicar a versão comercial e iniciar aquisição de clientes.

## Próximo passo

O simulador gratuito do WhatsApp/Meta já gera webhooks assinados de entrada, duplicidade e status pelo mesmo endpoint da produção, com bloqueio de destinos externos.

O simulador gratuito da IA está alinhado ao preflight real: considera perfil, base de conhecimento e cota para indicar resposta local, uso futuro do provedor ou transferência, sem chamada externa nem reserva de cota.

O armazenamento pago também pode ser homologado sem custo: o MinIO local implementa o mesmo contrato S3 do R2 e possui uma prova automatizada de gravação, leitura íntegra e remoção.

Os e-mails transacionais também podem ser homologados gratuitamente: o Mailpit captura o SMTP local e a prova automatizada confere destinatário, assunto e conteúdo sem entrega externa.

O procedimento de continuidade possui agora uma prova local: cria dump completo, restaura em banco temporário isolado, compara migration e todas as contagens e remove o ambiente de restauração sem alterar a origem.

As dependências externas estão classificadas em `EXTERNAL_DEPENDENCIES.md`. Meta, OpenAI, hospedagem pública, R2 e SMTP ainda exigem uma validação real; cobrança automática e infraestrutura definitiva continuam adiadas. Nenhum serviço deve ser ativado antes de empresa, data e limite financeiro do piloto estarem definidos.

A auditoria técnica está registrada em `AUDIT_PILOT_2026-08-31.md`: 44 testes, Ruff, migrations, build Docker, usuário não administrativo e proteção de configuração foram aprovados. O candidato ainda não está congelado devido à árvore Git não consolidada, legado empacotado, dependências sem lock e aceitação manual pendente.

O núcleo legado Flask/SQLite foi revisado e retirado depois de confirmar que menu, perfil comercial, documentos, transferência, protocolos e histórico já estão cobertos pela arquitetura atual.

A árvore de entrega foi classificada: código moderno e documentação formam o produto; dados JSON/SQLite, uploads e PDFs de teste foram retirados; ambientes, backups, builds e materiais de trabalho estão ignorados. Nenhum commit foi criado sem autorização.

As dependências diretas e transitivas estão travadas separadamente para produção e desenvolvimento. O Docker usa o lock de produção; a atualização controlada e a futura inclusão de hashes estão documentadas em `DEPENDENCIES.md`.

O gate com dependências travadas foi aprovado: imagem Docker construída, dependências internas consistentes, aplicação importada no contêiner, Ruff aprovado e 44 testes concluídos.

O primeiro conjunto consolidado da arquitetura moderna já foi versionado. A homologação local
funcional em desktop está registrada em `LOCAL_ACCEPTANCE_2026-09-04.md`.

As jornadas funcionais críticas em desktop e largura móvel foram aprovadas localmente.

Próximo passo: ampliar a validação local das recuperações de indisponibilidade. Depois disso, a
evolução do piloto passa a depender da definição de empresa, data e orçamento para provisionar a
homologação externa.
