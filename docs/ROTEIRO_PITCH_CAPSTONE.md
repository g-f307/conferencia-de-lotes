# Roteiro do pitch final do Capstone

## Parâmetros

- duração planejada: **9 minutos e 30 segundos**;
- três papéis genéricos: Apresentadores 1, 2 e 3;
- demonstração local, com massa sintética;
- nenhuma alegação de acesso, deploy ou homologação no Smart Office real.

## Roteiro cronometrado

| Tempo | Responsável | Slide/ação | Fala essencial |
|---|---|---|---|
| 0:00–0:45 | Apresentador 1 | Problema e objetivo | “Conferimos lotes combinando estoque desktop e pedidos web. A decisão é determinística; o ML apenas sugere a causa provável das divergências.” |
| 0:45–1:45 | Apresentador 1 | Abrir `docs/DIAGRAMAS_CAPSTONE.md` | Mostrar os seis bots, o fan-out das coletas, o fan-in da consolidação e a separação entre execução local e Smart Office futuro. |
| 1:45–2:35 | Apresentador 2 | Mostrar simulador desktop e Page Object web | Explicar que a coleta desktop usa interação visual e que o portal usa Playwright, locators semânticos e waits por condição. Não abrir sistema externo. |
| 2:35–4:15 | Apresentador 2 | Executar pipeline nominal local | Mostrar correlação, prioridades, predecessoras e término dos seis papéis. Destacar que o status já existe antes do ML. |
| 4:15–5:25 | Apresentador 3 | Executar uma sabotagem | Derrubar/simular indisponibilidade do ML. Mostrar fallback, continuidade do relatório e ausência de alteração no status determinístico. |
| 5:25–6:35 | Apresentador 3 | Abrir relatório e evidências | Mostrar Excel/Markdown/PDF/JSON, origem da sugestão, confiança, logs sanitizados e evidência de dead letter quando aplicável. |
| 6:35–7:25 | Apresentador 1 | Mostrar fallback de alertas | Explicar Telegram e SMTP opcionais e o log local como caminho final. Não afirmar envio real se nenhum canal externo tiver sido configurado. |
| 7:25–8:15 | Apresentador 1 | Mostrar coexistência | Demonstrar lease, fencing token e `shadow`: uma execução oficial produz efeitos e a comparativa não duplica publicação. |
| 8:15–9:00 | Apresentador 2 | Abrir índice de evidências | Relacionar critérios, testes, comandos e artefatos. Mostrar os hashes/relatório estrutural dos seis ZIPs. |
| 9:00–9:30 | Apresentador 3 | Limitações e próximos passos | “Tudo foi homologado localmente. O cadastro, smoke test, cutover e rollback no Smart Office não foram executados por falta de acesso e permanecem documentados como próximos passos.” |

## Comandos preparados

Antes da apresentação, gerar os artefatos fora do repositório:

```bash
python scripts/build_smart_office_packages.py --output-dir dist/capstone
python scripts/validate_smart_office_packages.py --package-dir dist/capstone
sha256sum dist/capstone/*.zip
python -m pytest tests/e2e/test_capstone_orchestration_pipeline_e2e.py -v
python -m pytest tests/e2e/test_crisis_pipeline_e2e.py -v --capstone-evidence-dir=dist/evidencias-capstone
python scripts/validate_capstone_crisis_evidence.py dist/evidencias-capstone
```

## Plano offline

Se navegador, desktop gráfico ou rede falharem:

1. não improvisar acesso a site externo;
2. abrir as amostras sanitizadas em `docs/evidencias/capstone/`;
3. abrir `dist/evidencias-capstone/resumo_cenarios.json`, gerado no ensaio;
4. mostrar o último relatório local e a saída da validação dos seis pacotes;
5. executar apenas os testes unitários de orquestração, que não dependem de GUI;
6. declarar que se trata de evidência pré-gerada no ensaio local.

## Checklist do ensaio

- [ ] O ensaio terminou em até 9 minutos e 30 segundos.
- [ ] Cada apresentador conhece sua troca de fala.
- [ ] Massa e logs estão sanitizados.
- [ ] Os artefatos foram gerados pelo commit apresentado.
- [ ] A sabotagem escolhida foi executada antes da apresentação.
- [ ] Nenhuma tela ou fala sugere homologação real no Smart Office.
