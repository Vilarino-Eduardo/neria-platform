# Auditoria técnica do candidato a piloto — 31/08/2026

## Resultado

O protótipo moderno está funcional e reproduzível, mas ainda não deve receber a marca de candidato
a piloto. Não há falha funcional bloqueante conhecida; as pendências estão na consolidação do
código-fonte, remoção segura do legado, reprodutibilidade das dependências e aceitação manual.

## Evidências aprovadas

- Ruff: todos os arquivos de aplicação, testes e scripts aprovados.
- Pytest: 44 testes aprovados.
- Alembic: modelos e migration `f2a761d48c0b` sincronizados.
- Docker: imagem `neria:audit-local` construída com sucesso.
- Contêiner: configurado para executar como usuário não administrativo `neria`.
- Configuração de produção: valores inseguros são recusados na inicialização.
- Segredos: nenhum padrão de chave privada ou token conhecido encontrado nos arquivos versionados.
- `.env`, backups, armazenamento local e ambiente virtual estão ignorados pelo Git.

## Achados por prioridade

### Resolvido — árvore de entrega classificada

A implementação moderna, as exclusões do esboço e os artefatos locais foram classificados. Dados
SQLite/JSON, uploads e PDFs de teste saíram da linha de base; ambientes, backups, builds Python e
materiais de trabalho estão ignorados. Falta somente criar o commit quando autorizado.

### Alta — aprovação manual ainda pendente

Os testes automatizados e a revisão técnica responsiva passaram, mas a jornada crítica e os estados
de indisponibilidade ainda precisam de aprovação humana em desktop e celular, conforme o checklist.

### Resolvido — núcleo legado não é mais empacotado

O conjunto Flask/SQLite foi revisado. Menu, perfil comercial, documentos, transferência, protocolos
e histórico já estavam cobertos pelo núcleo atual. Os módulos desconectados e o banco SQLite antigo
foram removidos; FastAPI, PostgreSQL e os serviços atuais permanecem como única linha de execução.

### Resolvido — dependências com versões travadas

O `pyproject.toml` mantém os intervalos de compatibilidade e os locks de produção e desenvolvimento
registram todas as versões transitivas exatas. O Docker instala o lock antes de copiar a aplicação,
melhorando reprodutibilidade e cache. A inclusão de hashes ficou documentada como evolução de CI.

### Baixa — aviso de compatibilidade nos testes

A suíte emite um aviso de descontinuação da integração entre o TestClient do Starlette e `httpx`.
Não afeta o funcionamento atual, mas deve ser tratado junto da próxima atualização de dependências.

## Itens externos já conhecidos

Hospedagem pública, Meta, OpenAI, R2 e SMTP real permanecem fora desta auditoria local e seguem a
ordem definida em `EXTERNAL_DEPENDENCIES.md`.

## Veredito

**Base técnica aprovada; candidato a piloto ainda não congelado.**

Próxima ação recomendada: revisar e retirar o legado isolado, ajustar exclusões do Git e então criar
uma linha de base limpa. Depois disso, travar dependências e repetir esta auditoria.
