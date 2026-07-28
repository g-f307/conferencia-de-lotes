# Revisão do BPMN e do PDD

## Registro

| Item | Informação |
|---|---|
| Data da revisão técnica | 27 de julho de 2026 |
| Escopo | Processo AS-IS, processo TO-BE, RN01–RN07 e implementação integrada |
| BPMN | `docs/diagrama_pdd.bpmn` |
| Visualização | `docs/diagrama_pdd.svg` |
| Regras-base | `docs/Regras de validação a aplicar - Gabriel, Marcelo e Rebecca.docx.pdf` |
| Massa-base | `docs/Inspeção de Lotes - Gabriel, Marcelo e Rebecca.xlsx` |
| Revisão cruzada | Deve ser confirmada por outro integrante no Pull Request da Issue #21 |

## Objetivo

Confirmar que o processo modelado e as regras documentadas continuam coerentes
com a automação integrada após Dispatcher, Performer, BotCity Maestro, Vault,
logs estruturados e Selenium.

## Aderência do processo

| Elemento do processo | Implementação | Situação |
|---|---|---|
| Receber planilha de inspeção | O bot inicia com um CSV previamente colocado em `dados_entrada/`. | Parcial; e-mail e download permanecem externos. |
| Validar estrutura e preenchimento | Dispatcher valida o cabeçalho; RN01 e RN02 validam o item. | Atendido. |
| Verificar lote na referência | RN03 usa `REFERENCE_LOTES`. | Atendido. |
| Normalizar status | RN05 converte `OK` e `NOK`. | Atendido. |
| Identificar status ambíguo | RN06 separa o item para revisão humana. | Atendido. |
| Continuar os demais registros | O Performer trata cada item isoladamente. | Atendido. |
| Exigir observação na reprovação | RN07 rejeita reprovação sem observação. | Atendido. |
| Gerar relatório consolidado | `ExecutionResult` gera `resumo_execucao.json`. | Atendido. |
| Atualizar sistema | O DataPool recebe o resultado; o ERP real não é atualizado. | Parcial e explicitamente fora do escopo. |
| Produzir evidência | Selenium valida o formulário controlado e gera PNG. | Atendido no ambiente de homologação. |

## Rastreabilidade das regras

| Regra | Código principal | Resultado |
|---|---|---|
| RN01 | `validate_columns` | Erro de negócio. |
| RN02 | `validate_required_fields` | Erro de negócio. |
| RN03 | `validate_lote_in_reference` | Erro de negócio. |
| RN04 | `validate_status` | Erro de negócio para status não oficial. |
| RN05 | `normalize_status` | Status normalizado antes da decisão. |
| RN06 | `HumanReviewStatus` | Revisão humana, sem estado final “pendente”. |
| RN07 | `validate_observation_for_reproved` | Erro de negócio. |

## Decisões consolidadas

1. O cenário oficial do projeto é conferência de lotes. Referências genéricas a
   usuários ou CPF pertenciam ao exemplo didático inicial.
2. Cada linha do CSV representa um item do DataPool.
3. O DataPool atual é `FilaAuditoriaLotes2`.
4. A credencial atual é `credencial_erp2`.
5. `APROVADO` e `REPROVADO` são os únicos status finais oficiais.
6. Status ambíguo não é convertido em resultado oficial pelo bot; o item é
   separado para revisão humana.
7. Erros de negócio não interrompem o restante da fila.
8. A senha do ERP é recuperada exclusivamente do Credentials Vault.
9. O formulário Selenium é uma evidência técnica controlada, não um ERP real.

## Diferenças conhecidas

### Aquisição da entrada

O BPMN inicia pelo recebimento de e-mail e planilha. A automação implementada
começa depois dessa etapa, com um CSV disponível em `dados_entrada/`. Captura de
e-mail, download de anexo e conversão de XLSX não foram implementados.

### Revisão humana

O BPMN representa a correção manual dos casos ambíguos. O código identifica e
registra esses casos, mas não oferece interface para a correção. O tratamento
posterior continua sob responsabilidade do analista.

### Atualização do sistema

O DataPool e os artefatos do Maestro são atualizados. A escrita em ERP foi
simulada pelo formulário local e permanece fora do escopo produtivo.

## Conclusão

O BPMN permanece adequado como visão do processo AS-IS e TO-BE. Não foi
necessário alterar o arquivo-fonte nesta revisão, pois os desvios existentes são
limites de escopo já documentados, e não mudanças nas regras ou decisões do
processo.

Os diagramas Mermaid em `README.md` e `docs/ARQUITETURA.md` complementam o BPMN
com a visão técnica dos componentes e da sequência executada pelo software.
