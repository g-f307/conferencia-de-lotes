# Revisão do BPMN e do PDD

## Registro

| Item | Informação |
|---|---|
| Data | 29 de julho de 2026 |
| Escopo | BPMN, RN01–RN07, DataPool, Playwright, Page Objects e evidências por item |
| BPMN | `docs/diagrama_pdd.bpmn` |
| Visualização | `docs/diagrama_pdd.svg` |
| Regras-base | `docs/Regras de validação a aplicar - Gabriel, Marcelo e Rebecca.docx.pdf` |
| Massa-base | `docs/Inspeção de Lotes - Gabriel, Marcelo e Rebecca.xlsx` |

## Objetivo

Confirmar que o processo e as regras continuam coerentes após a integração da
automação Playwright ao processamento individual do DataPool.

## Aderência

| Elemento do processo | Implementação | Situação |
|---|---|---|
| Receber planilha | A execução começa com CSV em `dados_entrada/`. | Parcial; e-mail e conversão permanecem externos. |
| Validar estrutura | Dispatcher e RN01–RN02. | Atendido. |
| Verificar referência | RN03 usa `REFERENCE_LOTES`. | Atendido. |
| Normalizar status | RN05 normaliza `OK` e `NOK`. | Atendido. |
| Separar ambiguidade | RN06 encaminha para revisão. | Atendido. |
| Continuar após falha | `LotePerformer` isola cada item. | Atendido. |
| Exigir observação | RN07 valida reprovação. | Atendido. |
| Interagir com sistema | Aplicação local por Playwright e Page Objects. | Atendido no ambiente controlado. |
| Produzir evidência | PNG aprovado, reprovado, divergente ou erro por item. | Atendido. |
| Atualizar resultado | Três campos de saída no DataPool. | Atendido. |
| Consolidar execução | JSON, PDF e logs estruturados. | Atendido. |

## Rastreabilidade das regras

| Regra | Código | Resultado |
|---|---|---|
| RN01 | `validate_columns` | erro de negócio |
| RN02 | `validate_required_fields` | erro de negócio |
| RN03 | `validate_lote_in_reference` | erro de negócio |
| RN04 | `validate_status` | erro de negócio |
| RN05 | `normalize_status` | status normalizado |
| RN06 | `HumanReviewStatus` | revisão humana |
| RN07 | `validate_observation_for_reproved` | erro de negócio |

## Decisões consolidadas

1. Cada linha do CSV representa um item do DataPool.
2. O DataPool é `FilaAuditoriaLotes2`.
3. A credencial é `credencial_erp2`.
4. `APROVADO` e `REPROVADO` são os estados finais de negócio.
5. Um estado ambíguo não é transformado em aprovação ou reprovação.
6. Divergências e falhas isoladas não interrompem a fila.
7. A senha é recuperada exclusivamente pelo Vault em integração real.
8. A interface web é local, controlada e não representa um ERP produtivo.
9. O resultado de negócio é calculado antes da apresentação na interface.
10. Page Objects não contêm RN01–RN07.

## Impacto da integração Playwright

A mudança substitui a tecnologia de automação e integra a evidência ao item,
sem alterar as decisões representadas no BPMN.

| Componente | Responsabilidade |
|---|---|
| `src/main.py` | preparar o ambiente, abrir a sessão e consolidar a execução |
| `src/bot.py` | classificar e processar cada item |
| `src/web_automation.py` | manter a sessão autenticada e produzir a captura |
| `LoginPage` | autenticar com locators semânticos |
| `FormPage` | apresentar o lote, aguardar o resultado e capturar a tela |
| `src/validation.py` | manter RN01–RN07 fora da camada web |

O BPMN não precisou ser alterado porque o evento inicial, as decisões de
negócio, o isolamento dos itens e o resultado esperado permanecem os mesmos. A
mudança é arquitetural e está detalhada em `docs/ARQUITETURA.md`.

## Diferenças conhecidas

### Aquisição da entrada

O processo modelado inicia com e-mail e planilha. A automação começa com um CSV
disponível em `dados_entrada/`.

### Revisão humana

O software identifica e registra o item, mas não oferece uma interface para a
decisão posterior do analista.

### Sistema corporativo

O DataPool e os artefatos do Maestro são atualizados. A interação de interface
ocorre somente na aplicação local controlada.

## Conclusão

O BPMN permanece adequado como visão de negócio. A integração final melhora a
rastreabilidade técnica ao relacionar resultado, log e evidência visual com
cada item, sem mover regras para a interface ou acessar um sistema real.

## Impacto do Relatório Executivo Excel (Aula 22)

A entrega da Aula 22 adiciona um fluxo paralelo focado na consolidação, validação completa (RN01-RN12) e apresentação de resultados gerenciais no Excel.

### O que muda:
1. **Nova capacidade de entrada**: O sistema agora também suporta a leitura direta das abas diárias do arquivo `Inspeção de Lotes - Gabriel, Marcelo e Rebecca.xlsx`.
2. **Avaliação estendida**: As validações agora englobam o conjunto total de regras (RN01-RN12), identificando falhas de padronização, ambiguidade e divergências de produto.
3. **Consolidação em Dashboard**: O resultado final é entregue em uma nova planilha formatada, com abas segmentadas por classificação e um dashboard nativo gerencial.

### O que não muda (sem impacto no fluxo orquestrado original):
- O fluxo web Playwright e a esteira baseada no BotCity DataPool continuam idênticos e isolados.
- O mapeamento BPMN anterior permanece fiel ao processo de conferência individual de lote, enquanto o fluxo Excel representa um procedimento analítico pós-processamento (ou um cenário alternativo não orquestrado de auditoria em lote).
