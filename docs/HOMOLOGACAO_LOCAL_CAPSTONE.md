# Empacotamento e homologação local dos seis bots

## Limite da evidência

Esta homologação comprova localmente o contrato dos seis bots, o conteúdo dos
pacotes e o comportamento do gateway em memória. Ela não representa cadastro,
execução ou homologação no Smart Office, ao qual a equipe não possui acesso.

## Pacotes

O manifesto versionado em `deployment/capstone_bots.json` é a fonte única para
nome, versão, entrypoint, prioridades, predecessores, timeout, capacidade do
Runner, variáveis e artefatos. Cada ZIP contém na raiz:

- `bot.py` independente;
- `requirements.txt` específico;
- `package-manifest.json` com o snapshot do contrato.

O código necessário permanece em `src/`. Testes, caches, logs, evidências,
bancos locais e `.env` são excluídos. Os ZIPs são determinísticos: duas
compilações do mesmo commit produzem o mesmo SHA-256.

| Bot | Smart Office | Prioridade local | Dependências | Runner lógico |
| --- | ---: | ---: | --- | --- |
| `dispatcher-v2` | 3 | 50 | nenhuma | Python |
| `estoque-desktop-v1` | 1 | 100 | Dispatcher | Windows com sessão gráfica |
| `fornecedores-web-v1` | 3 | 50 | Dispatcher | Python, Playwright e Chromium |
| `consolidacao-v2` | 3 | 50 | Desktop e Web | Python |
| `classificador-ml-v1` | 3 | 50 | Consolidação | Python com acesso HTTP opcional |
| `relatorio-alertas-v2` | 3 | 50 | Classificador | Python |

A escala documentada do Smart Office usa `1` como prioridade mais alta. O
gateway local existente usa números maiores para indicar maior prioridade;
por isso `100/50` é traduzido para `1/3`, sem alterar a ordem relativa.

## Geração e validação

```bash
python scripts/build_smart_office_packages.py
python scripts/validate_smart_office_packages.py
```

Os artefatos são gravados em `dist/capstone/`, diretório ignorado pelo Git. O
validador exige exatamente os seis ZIPs esperados, compara o manifesto interno
e rejeita arquivos potencialmente sensíveis ou indevidos.

## Homologação funcional local

```bash
python -m pytest tests/unit/test_capstone_packages.py -v
python -m pytest tests/unit/test_consolidation_main.py -v
python -m pytest tests/integration/test_capstone_orchestration.py -v
python -m pytest tests/e2e/test_capstone_orchestration_pipeline_e2e.py -v
```

O gateway em memória mantém `execution_id`, `correlation_id`, IDs locais das
tasks, fan-out, fan-in, prioridade, timeout, cancelamento e continuidade
degradada. O controle de coexistência testa idempotência e impede publicação
duplicada. Telegram e SMTP reais são opcionais; seus segredos ficam somente no
`.env` local e os testes automatizados usam adaptadores controlados.

## Evidências permitidas

Podem ser anexados ao PR os hashes impressos pelo build, a listagem interna dos
ZIPs e os relatórios de testes. Tokens, senhas, conteúdo do `.env`, endereços
pessoais e logs não sanitizados nunca devem ser anexados.
