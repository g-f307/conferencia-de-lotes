# Evidência do E2E do portal com Chromium

Execução realizada em **28 de agosto de 2026**, no Windows, utilizando o Chromium real disponibilizado pelo Playwright.

## Comando executado

```powershell
python -m pytest tests/e2e/test_supplier_portal_e2e.py -v
```

## Resultado

- Autenticação e coleta dos pedidos pelo Page Object: `PASSED`.
- Diferenciação de falha de autenticação: `PASSED`.
- Execução completa do coletor independente: `PASSED`.
- Resultado consolidado: `3 passed`.
- Navegador: `chromium` real, iniciado pelo fixture do Playwright.

## Escopo documental do PR

A alteração do `README.md` está limitada à execução do bot independente de fornecedores, ao contrato de saída e às variáveis de configuração introduzidas nesta entrega. Por estar diretamente vinculada à operação e à validação do componente, ela permanece neste PR.
