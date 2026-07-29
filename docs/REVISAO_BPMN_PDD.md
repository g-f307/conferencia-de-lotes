# Revisão do BPMN e do PDD

## Registro

| Item | Informação |
|---|---|
| Data da revisão técnica | 29 de julho de 2026 |
| Escopo | Processo AS-IS, processo TO-BE, RN01–RN07, Page Objects e implementação integrada |
| BPMN | `docs/diagrama_pdd.bpmn` |
| Visualização | `docs/diagrama_pdd.svg` |
| Regras-base | `docs/Regras de validação a aplicar - Gabriel, Marcelo e Rebecca.docx.pdf` |
| Massa-base | `docs/Inspeção de Lotes - Gabriel, Marcelo e Rebecca.xlsx` |
| Revisão cruzada | Deve ser confirmada por outro integrante no Pull Request da Issue #34 |

## Objetivo

Confirmar que o processo modelado e as regras documentadas continuam coerentes
com a automação integrada após Dispatcher, Performer, BotCity Maestro, Vault,
logs estruturados e a refatoração Selenium com Page Objects.

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

## Estratégia técnica com Page Objects

A refatoração Page Object altera a organização interna do software, sem
modificar as atividades, decisões ou responsáveis representados no BPMN.

As responsabilidades foram distribuídas da seguinte forma:

| Componente | Responsabilidade |
|---|---|
| `src/main.py` | Coordenar configuração, Vault, etapa web, Dispatcher, Performer e encerramento. |
| `src/web_automation.py` | Criar e encerrar o WebDriver, instanciar os Page Objects e sequenciar o fluxo web. |
| `src/pages/login_page.py` | Encapsular locators, waits e ações da autenticação. |
| `src/pages/form_page.py` | Encapsular locators, preenchimento, confirmação e captura da evidência. |
| `src/validation.py` | Manter RN01–RN07 independentes da interface web. |

`LoginPage` e `FormPage` recebem a mesma instância do WebDriver e o mesmo
timeout. A credencial recuperada do Vault é entregue à `LoginPage` somente em
memória, e o ciclo de vida do navegador permanece sob responsabilidade de
`src/web_automation.py`.

O PNG comprova a interação com o formulário controlado. Ele é persistido em
`artefatos/`, enquanto o resultado dos lotes permanece no DataPool e o resumo
JSON é publicado separadamente no Maestro.

### Impacto no BPMN

Não foi necessário alterar `diagrama_pdd.bpmn` ou `diagrama_pdd.svg` porque:

- o evento inicial e o resultado esperado do processo permanecem os mesmos;
- as decisões e regras RN01–RN07 não foram alteradas;
- Dispatcher, Performer, DataPool e revisão humana mantêm o comportamento;
- Page Object é um padrão de organização da camada de interface;
- o diagrama técnico em `docs/ARQUITETURA.md` registra a nova composição.

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
com a visão técnica dos componentes e da sequência executada pelo software. A
matriz em `docs/ADERENCIA_PAGE_OBJECTS.md` relaciona os requisitos da atividade
aos arquivos, testes e evidências correspondentes.
