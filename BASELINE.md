# Linha de base do produto

## Incluído no repositório

- API, worker e serviços da aplicação em `app/`.
- Interface web e ativos oficiais da Neria em `app/web/`.
- Migrations versionadas em `migrations/`.
- Testes automatizados em `tests/`.
- Ferramentas operacionais reproduzíveis em `scripts/`.
- Docker, configurações de exemplo e documentação do produto.

## Excluído da linha de base

- Segredos e configuração local em `.env`.
- Ambientes virtuais, caches, builds e metadados `egg-info`.
- Backups e arquivos armazenados localmente.
- Uploads e bancos/dados JSON ou SQLite do protótipo antigo.
- Materiais temporários de trabalho em `work/`.

## Estado desta consolidação

A árvore foi classificada e validada, mas ainda não foi adicionada ao stage nem transformada em
commit. Essas ações exigem autorização separada para preservar o controle sobre o histórico.
