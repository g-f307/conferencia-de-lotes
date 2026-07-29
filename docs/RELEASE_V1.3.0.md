# Conferência de Lotes v1.3.0

Esta versão consolida a adoção do padrão Page Object na automação Selenium e a
documentação técnica correspondente.

## Principais alterações

- criação da `LoginPage` para encapsular autenticação, locators e waits;
- criação da `FormPage` para encapsular o formulário de lotes;
- integração do fluxo `LoginPage` → `FormPage` à automação Selenium;
- remoção das interações Selenium diretas do orquestrador;
- compartilhamento do WebDriver e do timeout entre os Page Objects;
- uso da credencial recuperada pelo Credentials Vault no login web;
- proteção da senha contra exposição em logs, exceções e relatórios;
- manutenção da geração e validação das evidências PNG;
- atualização do README, da arquitetura e da revisão do PDD;
- criação da matriz de aderência da atividade;
- simplificação da apresentação pública da equipe.

## Validação

- 145 testes automatizados aprovados;
- cobertura total de 92,87%;
- execução local validada com Selenium desabilitado;
- execução local validada com Selenium habilitado;
- evidência PNG gerada e verificada;
- imagem Docker construída;
- execução via Docker Compose validada com Selenium;
- arquivos operacionais mantidos fora do Git.

## Evidências preservadas

| Evidência | Destino |
|---|---|
| Confirmação visual | `artefatos/comprovante-<lote>-<timestamp>.png` |
| Log estruturado | `logs/execucao.log` |
| Resumo consolidado | `relatorios/resumo_execucao.json` |
| Resultado individual | DataPool `FilaAuditoriaLotes2` |
| Resumo da task | Artefato JSON no BotCity Maestro |

## Compatibilidade

Esta versão não altera:

- regras RN01–RN07;
- contrato do CSV de entrada;
- estrutura do DataPool;
- labels `FilaAuditoriaLotes2` e `credencial_erp2`;
- argumentos recebidos do BotCity Runner;
- formato do resumo `ExecutionResult`.

Não há migração de dados ou alteração de configuração obrigatória para atualizar
da versão `v1.2.0`.
