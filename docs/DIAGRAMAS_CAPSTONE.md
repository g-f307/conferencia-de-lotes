# Diagramas finais do Capstone

## Legenda de estado

- **Azul/verde e linha contínua:** implementado e executado localmente.
- **Cinza e linha tracejada:** integração externa preparada, mas não executada.
- **Amarelo:** continuidade degradada ou revisão humana.

Nenhum diagrama desta página representa cadastro, deploy ou homologação no
Smart Office real.

## Arquitetura dos seis bots

```mermaid
flowchart LR
    D[1. dispatcher-v2] --> E[2. estoque-desktop-v1]
    D --> W[3. fornecedores-web-v1]
    E --> C[4. consolidacao-v2]
    W --> C
    C --> M[5. classificador-ml-v1]
    M --> R[6. relatorio-alertas-v2]
    C -->|ML desligado ou indisponível| R
    R --> A[Excel, Markdown, JSON, PDF e log]
    R -. integração opcional .-> N[Telegram / SMTP]
    SO[Smart Office real] -. estado-alvo não homologado .-> D

    classDef local fill:#e7f3ff,stroke:#1976d2,stroke-width:2px;
    classDef evidence fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef future fill:#f3f4f6,stroke:#6b7280,stroke-dasharray:5 5;
    class D,E,W,C,M,R local;
    class A evidence;
    class N,SO future;
```

## Sequência nominal

```mermaid
sequenceDiagram
    participant D as Dispatcher
    participant E as Estoque desktop
    participant W as Fornecedores web
    participant C as Consolidação
    participant M as ML opcional
    participant R as Relatório/alertas
    D->>E: contexto e correlação
    D->>W: contexto e correlação
    par coletas independentes
        E-->>C: estoque
        W-->>C: pedidos
    end
    C->>C: RN01-RN12 e regras CONS
    C->>M: somente divergências elegíveis
    M-->>R: causa, origem e confiança
    C-->>R: decisão determinística
    R-->>D: artefatos e término
```

## Fan-out e fan-in

```mermaid
flowchart LR
    D[Dispatcher] -->|fan-out, prioridade local 100| E[Desktop]
    D -->|fan-out, prioridade local 50| W[Web]
    E -->|sucesso ou falha terminal| G{Fan-in}
    W -->|sucesso ou falha terminal| G
    G --> C[Consolidação determinística]
    C --> O[Próximas etapas]
```

A escala local usa números maiores para maior prioridade. Na configuração-alvo
do Smart Office a escala documentada é inversa: `1` é a maior prioridade e `5`
a menor. O adaptador traduz a prioridade; o domínio não depende dessa escala.

## Continuidade degradada

```mermaid
flowchart TD
    S[Coleta ou dependência] --> T{Concluiu no prazo?}
    T -->|sim| C[Consolidar normalmente]
    T -->|não| R[Retry com limite e backoff]
    R --> F{Recuperou?}
    F -->|sim| C
    F -->|não| P[Fallback sanitizado]
    P --> V[PENDENTE_REVISAO]
    P --> DL[Dead letter idempotente]
    V --> O[Relatório em modo degradado]
    DL --> O
```

## Fallback de alertas

```mermaid
flowchart LR
    R[relatorio-alertas-v2] --> T{Telegram habilitado?}
    T -->|sim| TS[Enviar Telegram]
    T -->|não ou falha| E{SMTP habilitado?}
    TS -->|falha| E
    E -->|sim| ES[Enviar e-mail]
    E -->|não ou falha| L[Registrar alerta sanitizado no log]
    ES -->|falha| L
    TS --> OK[Registrar entrega]
    ES --> OK
```

Telegram e SMTP são integrações opcionais configuradas por `.env` local. O log
é o fallback sempre disponível e é a evidência reproduzível do repositório.

## Coexistência local e estado-alvo

```mermaid
flowchart LR
    M[Maestro / fluxo legado] --> G[Controle de coexistência]
    S[Gateway local compatível] --> G
    G -->|lease + fencing token| O[Proprietário oficial]
    G -->|sem efeito de negócio| H[Execução shadow]
    O --> P[Pipeline local]
    H --> P
    SO[Smart Office real] -. cadastro, cutover e rollback não executados .-> S

    classDef local fill:#e7f3ff,stroke:#1976d2,stroke-width:2px;
    classDef degraded fill:#fff8e1,stroke:#f9a825,stroke-width:2px;
    classDef future fill:#f3f4f6,stroke:#6b7280,stroke-dasharray:5 5;
    class M,G,O,S,P local;
    class H degraded;
    class SO future;
```

O lease persistente, a exclusão mútua e o modo `shadow` foram validados
localmente. Cutover, rollback e cadastro no Smart Office permanecem como
procedimentos preparados para execução futura por uma equipe com acesso.
