# Automação desktop de estoque do Capstone

## Objetivo e fronteira

`estoque-desktop-v1` consulta um sistema legado Windows controlado usando apenas
o que um operador enxerga e faz: reconhecer marcadores na tela, clicar no campo
de busca, digitar o filtro, confirmar a consulta e copiar a grade visível. O bot
não importa o simulador, não lê `SAMPLE_STOCK`, não consulta banco, arquivo ou
API da aplicação e não executa regras de negócio.

O simulador está em `src/desktop_stock/simulator.py`. Ele exibe exatamente os
campos definidos pela arquitetura:

```text
lote_id, produto, quantidade_disponivel, localizacao,
status_estoque, atualizado_em
```

## Componentes

| Componente | Responsabilidade |
|---|---|
| `StockSimulatorApp` | Representar o sistema legado em uma janela Tkinter controlada. |
| `DesktopDriver` | Isolar a interação visual e permitir testes determinísticos. |
| `PyAutoGuiDesktopDriver` | Reconhecer cores da tela e operar mouse, teclado, clipboard e screenshot no Windows. |
| `DesktopStockCollector` | Aplicar timeout, retry, parsing, evidência, log, fallback e contrato de saída. |
| `DesktopCollectionContext` | Receber os identificadores rastreáveis criados pelo Dispatcher. |

Os três marcadores coloridos pertencem somente à interface. O driver os encontra
na captura de tela por pixels e calcula as posições dos controles. Isso evita
coordenadas absolutas fixas, mas continua sendo automação visual: mover a janela
não fornece acesso interno ao simulador.

## Execução manual no Windows

Instale as dependências e abra o simulador:

```powershell
python -m pip install -r requirements.txt
python -m src.desktop_stock.simulator
```

Em outro terminal, mantenha a janela visível e execute o bot:

```powershell
$env:EXECUTION_ID = "desktop-demo-001"
$env:CORRELATION_ID = "capstone-demo-001"
$env:ROOT_TASK_ID = "dispatcher-demo-001"
$env:TASK_ID = "desktop-task-demo-001"
$env:PARENT_TASK_ID = "dispatcher-demo-001"
$env:EXPECTED_ITEMS = "5"
python -m src.desktop_stock.main --output data/output/desktop-stock.json
```

Para a demonstração automatizada, o E2E inicia o simulador, aguarda o marcador
visual, executa a coleta e encerra a aplicação em `finally`:

```powershell
$env:RUN_DESKTOP_E2E = "1"
python -m pytest tests/e2e/test_desktop_stock_e2e.py -v -s
```

O Runner deve possuir sessão gráfica desbloqueada e exclusiva. O bot não deve
ser executado por serviço Windows sem desktop interativo.

## Saída e evidências

O JSON segue o envelope `schema_version=1.0` definido em
`docs/ARQUITETURA_CAPSTONE.md`. No caminho nominal:

- `status=SUCCESS`;
- `source_status=AVAILABLE`;
- `origem_dados=["desktop"]`;
- `payload.records` contém somente os seis campos visíveis;
- `artifacts` registra a evidência PNG e seu SHA-256.

Os eventos de log registram início, tentativa, término ou fallback, contagem,
tentativas, latência e os identificadores de correlação. Textos de erro são
limitados e o coletor não registra conteúdo livre da tela.

## Timeout, retry e fallback

`LinearRetryPolicy` controla o número de tentativas, intervalo e timeout por
operação. A indisponibilidade persistente produz um resultado terminal seguro:

```text
status=PARTIALLY_COMPLETED
source_status=UNAVAILABLE
modo_degradado=true
motivo_fallback=desktop_unavailable_after_retry
```

O resultado não inventa registros. Quando `expected_items` é conhecido, eles
aparecem em `failed_items` para que a consolidação encaminhe o trabalho à revisão
humana. Evidências de tentativas malsucedidas são preservadas quando a tela pode
ser capturada. O bloco `finally` sempre libera teclas modificadoras do driver.

## Testes

```powershell
python -m pytest tests/unit/test_desktop_stock.py -v
python -m pytest tests/integration/test_desktop_stock_collection.py -v
python -m pytest tests/e2e/test_desktop_stock_e2e.py -v
```

O E2E real é propositalmente protegido por `RUN_DESKTOP_E2E=1`, pois exige uma
sessão gráfica Windows. A CI usa um driver injetável, exercita o mesmo contrato
e não necessita credenciais nem acesso externo.
