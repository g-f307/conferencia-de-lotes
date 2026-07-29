# Roteiro de demonstração

Tempo total sugerido: 10 minutos.

## Preparação

- usar somente massa e credenciais fictícias;
- deixar o ambiente virtual ativo;
- confirmar que `.env` e evidências não estão no Git;
- preparar itens que produzam aprovação e divergência;
- limpar somente saídas da demonstração anterior.

## Sequência

### 1. Contexto e versão — 1 minuto

- mostrar a branch da entrega;
- resumir objetivo e limites;
- destacar que a aplicação web é local e controlada.

### 2. Arquitetura — 2 minutos

- abrir `src/pages/login_page.py`;
- abrir `src/pages/form_page.py`;
- mostrar locators semânticos e waits;
- abrir `src/web_automation.py`;
- explicar que RN01–RN07 permanecem em `src/validation.py`.

### 3. Entrada e segurança — 1 minuto

- mostrar os campos do DataPool;
- mostrar a massa de entrada;
- mostrar apenas o label do Vault;
- reforçar que a senha não está no código nem no `.env`.

### 4. Execução — 3 minutos

```bash
python bot.py
```

Durante a execução:

- indicar a sessão Playwright headless;
- acompanhar os itens no log;
- mostrar que uma divergência não interrompe o próximo lote;
- confirmar a finalização operacional.

### 5. Evidências — 2 minutos

- abrir um PNG `aprovado-*`;
- abrir um PNG `divergencia-*`;
- mostrar os campos `resultado_validacao`, `evidencia` e
  `mensagem_resultado` no DataPool;
- abrir `resumo_execucao.json`;
- mostrar o relatório PDF.

### 6. Encerramento — 1 minuto

- mostrar o README e a revisão do PDD;
- explicar limitações;
- indicar próximos passos.

## Limitações

- a entrada por e-mail e XLSX não está automatizada;
- a aplicação web não é um ERP real;
- revisões humanas são identificadas, mas não resolvidas pelo bot;
- disponibilidade do navegador depende do ambiente do Runner.

## Próximos passos

- integrar aquisição segura da entrada;
- criar interface para tratamento de revisão;
- ampliar telemetria e retenção de artefatos;
- homologar carga e concorrência em ambiente corporativo.
