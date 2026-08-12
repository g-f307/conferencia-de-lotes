# Homologacao do relatorio da Aula 22

## Dataset

- Entrada: `dados_entrada/inspecao_lotes_10dias.xlsx`
- Total consolidado: 250 registros
- Abas diarias: 10
- Registros por aba diaria: 25

## Resultado do servico de validacao

O enunciado informa 100 divergencias propositais. A implementacao nao fixa esse
valor no codigo e nao altera regras para alcancar uma contagem esperada.

Com as regras RN01-RN12 implementadas no `ValidationService`, o dataset fornecido
produz:

- Validos: 152
- Divergencias: 50
- Ambiguos: 20
- Erros de entrada: 28
- Registros problematicos: 98

Totais por regra:

- RN01: 2
- RN02: 2
- RN03: 2
- RN04: 2
- RN05: 10
- RN09: 20
- RN10: 21
- RN11: 20
- RN12: 20

Como um registro pode possuir multiplas violacoes, os totais por regra nao devem
ser somados como se fossem registros unicos. A classificacao final usa a
precedencia definida no servico: erro de entrada, divergencia, ambiguo e valido.

## Observacao

A diferenca entre os 100 problemas citados no enunciado e os 98 registros
problematicos classificados pelo servico deve ser confrontada com o gabarito do
professor antes do merge final. Nenhuma regra foi modificada para forcar esse
total.
