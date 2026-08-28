# Evidência do E2E desktop em Windows

Execução realizada em **28 de agosto de 2026**, em uma sessão gráfica real do Windows, usando o simulador de estoque e o driver PyAutoGUI.

## Comando executado

```powershell
$env:RUN_DESKTOP_E2E = "1"
$env:DESKTOP_E2E_EVIDENCE_DIR = "docs/evidencias/capstone/desktop-windows"
python -m pytest tests/e2e/test_desktop_stock_e2e.py -v -s
```

## Resultado

- Cenário executado: coleta visual do estoque pelo simulador desktop.
- Resultado: `1 passed`.
- Evidência: [`desktop-e2e-desktop-attempt-1.png`](desktop-e2e-desktop-attempt-1.png).
- Validação automática: o teste exige que o PNG exista e possua conteúdo após `capture_evidence()`.

A captura é restrita à janela do simulador de estoque em primeiro plano, evitando registrar outras aplicações abertas no ambiente do executor.
