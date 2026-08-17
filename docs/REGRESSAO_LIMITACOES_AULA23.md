# Regressão e limitações conhecidas — Aula 23

## Testes de regressão

Um teste marcado como `regression` protege um comportamento que já funciona ou
um defeito que não pode voltar. Esses testes são executados normalmente e uma
falha bloqueia a suíte.

As regressões críticas desta etapa protegem:

- RN07: normalização de `NOK` para `REPROVADO`;
- RN10: lote reprovado sem observação classificado como `Divergência`;
- precedência de `Divergência` sobre `Ambíguo` quando ambas as regras aparecem.

Execução isolada:

```bash
python -m pytest -m regression -v -rxX
```

## Quando usar skip

`skip` representa um teste que não pode ser executado porque a funcionalidade ou
o ambiente necessário ainda não existe. O corpo do teste não é executado.

Nesta etapa, a atualização incremental do workbook está marcada com `skip`. A
versão atual sempre reprocessa todas as abas e substitui o relatório final. O
marker deve ser removido somente quando existir uma API de atualização
incremental com comportamento testável.

## Quando usar xfail

`xfail` representa um comportamento executável que possui uma divergência real e
reproduzível. Diferentemente de `skip`, o teste é executado e sua falha esperada
aparece no relatório.

O enunciado da Aula 22 informa 100 registros problemáticos. A homologação atual
das RN01-RN12 sobre o workbook versionado encontra 98:

- 50 divergências;
- 20 ambíguos;
- 28 erros de entrada.

O teste usa `strict=True`: se passar inesperadamente, o Pytest retorna `XPASS`
como falha e exige revisão do marker. Ele também aceita somente a exceção
`DivergenciaGabaritoAula22`; erros de leitura, escrita ou outros totais continuam
falhando normalmente e não são escondidos pelo `xfail`.

O marker deve ser removido quando o gabarito for conciliado. As regras não devem
ser alteradas apenas para atingir artificialmente o total 100.

## Evidência no relatório

```bash
python -m pytest -m regression -v -rxX
python -m pytest -v -rsx
```

- `SKIPPED`: funcionalidade indisponível e teste não executado;
- `XFAIL`: divergência conhecida reproduzida como esperado;
- `XPASS`: comportamento mudou e o teste precisa ser revisado.

Consulte também `docs/HOMOLOGACAO_RELATORIO_AULA22.md` para os totais detalhados
por classificação e por regra.
