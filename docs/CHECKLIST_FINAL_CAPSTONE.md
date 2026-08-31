# Checklist final do Capstone

## Entrega técnica

- [x] Seis papéis de bot independentes definidos e empacotáveis.
- [x] Coleta desktop visual em simulador controlado.
- [x] Coleta web com Playwright e Page Object.
- [x] Fan-out, fan-in, prioridades, predecessoras e timeout.
- [x] Consolidação com decisão determinística antes do ML.
- [x] ML opcional com feature flag, confiança e fallback.
- [x] Relatórios Excel, Markdown, PDF e JSON e logs estruturados.
- [x] Retry, fallback, dead letter e continuidade degradada.
- [x] Alertas por Telegram e SMTP atrás de configuração opcional.
- [x] Fallback local de alertas testado sem credenciais externas.
- [x] Idempotência, lease, fencing token e modo `shadow`.
- [x] Seis sabotagens automatizadas e sanitizadas.
- [x] Pacotes determinísticos e validação estrutural com SHA-256.

## Documentação e rastreabilidade

- [x] README com visão, execução, limitações e documentos finais.
- [x] PDD atualizado para o pipeline híbrido final.
- [x] Diagramas nominal, fan-out/fan-in, degradação, alertas e coexistência.
- [x] Índice liga os critérios a código, teste, comando e artefato.
- [x] Roteiro divide o pitch de até dez minutos entre três apresentadores.
- [x] Plano offline definido.
- [x] `.env`, credenciais, logs e artefatos de runtime fora do Git.
- [x] Evidências versionadas usam apenas dados sintéticos e sanitizados.

## Estado de homologação

| Item | Estado | Observação |
|---|---|---|
| Pipeline completo | `ATENDIDO LOCALMENTE` | gateway local e pacotes compatíveis |
| Desktop e web | `ATENDIDO LOCALMENTE` | simuladores controlados |
| Telegram/SMTP reais | `OPCIONAL EXTERNO` | executar somente com credenciais autorizadas |
| Cadastro dos seis bots no Smart Office | `NÃO EXECUTADO — SEM ACESSO` | não existem IDs de deploy na entrega |
| Smoke test no Smart Office | `NÃO EXECUTADO — SEM ACESSO` | procedimento documentado |
| Cutover/rollback reais | `NÃO EXECUTADO — SEM ACESSO` | desenho e simulação local disponíveis |

## Conferência antes do PR/release

```bash
python -m ruff check --select E4,E7,E9,F api_ml bot.py gerar_relatorio.py src tests scripts
python -m pytest -m "not e2e and not browser" --cov=src --cov-report=term-missing --cov-fail-under=80
python -m pytest tests/e2e/test_capstone_orchestration_pipeline_e2e.py tests/e2e/test_crisis_pipeline_e2e.py -v
git diff --check
git status --short
```

- [ ] Anexar ou publicar o relatório de cobertura gerado pelo CI.
- [ ] Conferir os seis hashes impressos pelo build ou por `sha256sum`.
- [ ] Conferir `resumo_cenarios.json` e os seis cenários.
- [ ] Cronometrar o pitch final.
- [ ] Executar a revisão por pares; o grupo revisor preenche Sim/Não e observações.

## Limitações, riscos e próximos passos

1. A equipe não possui acesso operacional ao Smart Office; cadastro, smoke test,
   cutover e rollback reais dependem de autorização externa.
2. Telegram e SMTP exigem credenciais próprias. Sem elas, a demonstração usa
   adaptadores controlados e fallback para log.
3. Desktop real varia por resolução, tema e sessão gráfica; antes de produção,
   os marcadores visuais devem ser recalibrados no Runner autorizado.
4. A massa da demonstração é sintética e não substitui homologação com dados
   corporativos anonimizados.
5. Próximo passo: executar o roteiro de migração em ambiente autorizado,
   registrar IDs e evidências reais, validar observabilidade e só então aprovar
   o cutover.
