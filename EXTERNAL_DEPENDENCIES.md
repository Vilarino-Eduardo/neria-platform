# Dependências externas antes do piloto

Este mapa separa o que está homologado localmente do que só pode ser comprovado com serviços
reais. Nenhuma contratação ou ativação paga deve ocorrer antes de existir data e participante do
piloto.

## Validações reais obrigatórias

| Ordem | Dependência | O que o ambiente local já valida | O que ainda exige o serviço real |
|---|---|---|---|
| 1 | Hospedagem e domínio HTTPS | Docker, API, worker, health checks e migrations | Rede pública, TLS, variáveis, reinício e comunicação entre processos |
| 2 | Meta WhatsApp Cloud API | Assinatura, payloads, idempotência, status e recuperação | Número real, webhook público, credenciais, templates e entrega nos aparelhos |
| 3 | OpenAI | Roteamento, contexto, conhecimento, cotas e transferência | Qualidade, latência, consumo de tokens e comportamento do modelo selecionado |
| 4 | Armazenamento R2 | Contrato S3, gravação, leitura íntegra e remoção no MinIO | Credenciais, permissões, latência, retenção e acesso no provedor |
| 5 | SMTP transacional | Composição e captura das mensagens no Mailpit | Entrega, reputação, SPF, DKIM, DMARC e tratamento de rejeições |

Esses serviços podem oferecer franquias ou ambientes de teste, mas devem ser tratados como
potencialmente geradores de custo. Preços e limites serão conferidos somente no momento da
ativação.

## Custos que podem continuar adiados

- Cobrança automática: os planos já podem ser administrados manualmente no MVP.
- Infraestrutura de produção definitiva: o piloto deve começar em homologação controlada.
- Aquisição de clientes e campanhas: somente depois da aprovação operacional.
- Ferramentas avançadas de observabilidade: logs e health checks atuais bastam para o piloto.
- Funcionalidades pessoais da Neria e integrações externas da IA: fora do MVP comercial atual.

## Trabalho gratuito ainda possível

- Executar a suíte completa e verificar migrations e imagem Docker.
- Fazer revisão final de segurança, segredos e configurações de produção.
- Aprovar manualmente as jornadas em desktop e celular.
- Exercitar falhas de Meta, SMTP, armazenamento, banco e worker com os simuladores locais.
- Remover código legado apenas após confirmar que não contém regras úteis.
- Congelar oferta inicial, limites, onboarding e materiais comerciais.

## Gatilho para iniciar custos

Ativar serviços reais somente quando houver:

1. empresa piloto e responsável definidos;
2. janela de homologação agendada;
3. limite financeiro aprovado;
4. critérios de interrupção definidos;
5. responsável por acompanhar consumo e incidentes.

## Ordem recomendada de ativação real

1. Hospedagem, banco, Redis e domínio HTTPS.
2. R2 e rotina de backup externo.
3. SMTP real.
4. Número de teste da Meta.
5. OpenAI por último, com cota diária baixa e alertas.

Essa ordem deixa a infraestrutura observável antes de liberar os dois componentes com consumo
variável: mensagens da Meta e chamadas ao modelo.
