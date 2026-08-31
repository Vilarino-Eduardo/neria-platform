# Empresa demonstrativa

O gerador cria uma empresa fictícia isolada com perfil, administrador, conversas, contatos, etiquetas, conhecimento, automação e configuração segura da IA.

No PowerShell:

```powershell
$env:NERIA_DEMO_PASSWORD = "escolha-uma-senha-segura"
.\.venv\Scripts\python.exe scripts\seed_demo.py
```

Credenciais:

- E-mail: `demo@neria.local`
- Senha: valor definido em `NERIA_DEMO_PASSWORD`

O WhatsApp demonstrativo permanece desconectado. Assim, nenhuma ação da apresentação pode enviar mensagens reais ou consumir serviços externos.

O comando recusa substituir uma demonstração existente. Para remover somente essa empresa:

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py --remove
```

Depois de removê-la, execute novamente o primeiro comando para recriar os mesmos cenários com dados limpos.

## Simular o WhatsApp sem custo

Com a API local em execução e uma conta demonstrativa cadastrada, copie o **ID do número**
mostrado na tela WhatsApp e execute:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_whatsapp.py --phone-number-id "SEU_ID_DO_NUMERO" --text "Olá, preciso de ajuda" --duplicate
```

O primeiro webhook deve retornar `accepted` e a repetição, `duplicate`. O comando valida a
assinatura e percorre o mesmo endpoint usado pela Meta. Por segurança, ele recusa endereços que
não sejam locais e nunca chama a API externa do WhatsApp.

Para simular a confirmação de leitura de uma mensagem enviada, use o identificador externo dela:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_whatsapp.py --phone-number-id "SEU_ID_DO_NUMERO" --status read --message-id "wamid.ID_DA_MENSAGEM"
```

## Homologar o armazenamento sem custo

Inicie o MinIO local e execute a prova de integridade:

```powershell
docker compose up -d minio minio-init
.\.venv\Scripts\python.exe scripts\simulate_object_storage.py
```

O teste grava, recupera, compara e remove um arquivo temporário. O painel local do MinIO fica em
`http://localhost:9001`. Para fazer a aplicação usar esse serviço durante testes, altere apenas
`OBJECT_STORAGE_BACKEND=s3`; as credenciais locais já estão documentadas no `.env.example`.

## Homologar e-mails sem entrega externa

Inicie o capturador SMTP local e execute a prova completa:

```powershell
docker compose up -d mailpit
.\.venv\Scripts\python.exe scripts\simulate_email.py
```

O e-mail fica disponível somente no painel `http://localhost:8025`. Para testar a recuperação de
senha pela própria interface, use `SMTP_HOST=localhost`, `SMTP_PORT=1025` e
`SMTP_USE_TLS=false`, conforme o `.env.example`.

## Validar backup e restauração sem custo

Com o PostgreSQL local em execução:

```powershell
.\.venv\Scripts\python.exe scripts\verify_backup_restore.py
```

O banco principal é somente lido. A restauração acontece em um banco temporário isolado, que é
removido após a comparação de todas as tabelas. O dump validado permanece na pasta `backups/`.
