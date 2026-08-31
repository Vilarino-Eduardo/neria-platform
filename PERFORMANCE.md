# Testes de desempenho

O teste cobre dashboard, caixa de entrada, notificações e etiquetas usando um tenant temporário.
Esse tenant é removido ao final da execução.

Com a API local ativa:

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py --temporary-tenant --requests 1000 --concurrency 25
```

Critérios iniciais do protótipo:

- menos de 1% de falhas;
- p95 inferior a 1 segundo;
- nenhuma resposta 5xx.

Esses limites deverão ser revistos em homologação, com latência de rede e volume representativo.

## Linha de base local

Medições realizadas em 28/08/2026, com PostgreSQL e Redis locais, logs assíncronos e o access log do Uvicorn desativado:

| Requisições | Concorrência | Falhas | Requisições/s | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|---:|---:|
| 1.000 | 10 | 0% | 31,76 | 276,38 ms | 547,70 ms | 947,11 ms |
| 1.000 | 25 | 0% | 26,37 | 902,03 ms | 1.558,29 ms | 2.291,41 ms |

O cenário de até 10 requisições concorrentes atende ao critério inicial. Com 25 requisições concorrentes não houve falhas ou respostas 5xx, mas o p95 ultrapassou 1 segundo. Essa é uma referência para otimização e dimensionamento antes da homologação, não um bloqueio para o protótipo.
