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

A interface do serviço de IA está desacoplada do fornecedor e a integração funcional foi construída
sobre conversas, automações e base de conhecimento. O protótipo já possui recuperação de fontes,
memória recente, limites de confiança e consumo, citações, proteção contra instruções maliciosas,
transferência humana, métricas e feedback. Aprendizado autônomo não faz parte do MVP: o feedback
aprovado forma a base segura para essa evolução futura sem permitir alterações não supervisionadas
no comportamento em produção.

## Estado atual — 08/09/2026

O núcleo do protótipo comercial está implementado: arquitetura multiempresa, autenticação, equipe,
contatos, atendimento humano, WhatsApp Cloud API, automações, base de conhecimento, IA com
transferência segura, métricas, auditoria, LGPD, Docker e contratos de armazenamento externo.
Essa cobertura funcional não equivale a um produto pronto para venda: as integrações externas e a
operação com empresas reais ainda não foram homologadas.

O gate técnico local atual possui 104 testes aprovados, Ruff aprovado, dependências consistentes,
migration `a7f3c91d2e64` aplicada e API, worker e beat executando a mesma imagem. A busca lexical da
base de conhecimento usa índice do PostgreSQL e permanece preparada para evolução híbrida/vetorial.

## Roadmap restante até a venda

### 1. Fechar o candidato local ao piloto — fase atual

- [x] Validar jornadas críticas em desktop e largura móvel.
- [x] Validar falhas de Meta, Redis e PostgreSQL sem perda de mensagens.
- [x] Validar backup/restauração, SMTP local e contrato S3 no ambiente gratuito.
- [x] Sincronizar código, migrations, API, worker e beat.
- [x] Aprovar a suíte atual de 104 testes e a análise estática.
- [x] Validar indisponibilidade do armazenamento na API, interface e tarefas críticas.
- [ ] Executar e registrar a avaliação real da IA depois das mudanças de recuperação.
- [ ] Publicar a linha de base atual no GitHub e confirmar o CI remoto.

### 2. Homologação externa

- [ ] Definir empresa piloto, responsáveis, data e teto financeiro.
- [ ] Provisionar ambiente HTTPS com PostgreSQL, Redis, R2, SMTP e backups.
- [ ] Demonstrar restauração no ambiente externo.
- [ ] Conectar um número real da Meta e validar recebimento, envio, status e templates.
- [ ] Validar qualidade, latência e custo da IA com limites baixos.

### 3. Piloto controlado

- [ ] Operar com uma a três empresas selecionadas.
- [ ] Acompanhar qualidade, transferências humanas, custo, carga e incidentes.
- [ ] Corrigir problemas bloqueantes sem ampliar o escopo do MVP.
- [ ] Congelar a primeira versão operacional aprovada.

### 4. Preparação comercial

- [ ] Definir oferta, preço, limites, termos de uso e política de privacidade.
- [ ] Finalizar identidade visual e textos comerciais.
- [ ] Criar landing page, demonstração guiada e materiais de onboarding e suporte.
- [ ] Manter cobrança manual no primeiro piloto; automatizá-la após validar o processo.

### 5. Lançamento profissional

- [ ] Realizar revisão final de segurança, privacidade e continuidade.
- [ ] Definir indicadores e compromissos de suporte e disponibilidade.
- [ ] Publicar a versão comercial e iniciar aquisição controlada de clientes.

## Próximo passo

Executar e registrar uma avaliação controlada da IA real depois das mudanças de recuperação de
conhecimento. Essa etapa usa poucas chamadas pagas e só deve começar com confirmação explícita.

As fronteiras que ainda exigem serviços reais permanecem registradas em
`EXTERNAL_DEPENDENCIES.md`. Ativações externas só devem ocorrer depois da definição do piloto e de
seu limite financeiro.
