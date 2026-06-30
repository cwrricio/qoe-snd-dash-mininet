# Relatório da Etapa 3 — Implementação do Controle via SDN

## Objetivo

Implementar no controlador SDN uma **lógica de detecção de degradação** e um
**mecanismo de mitigação** que melhore a QoE do streaming MPEG-DASH sob
congestionamento, **programando regras OpenFlow dinamicamente** e registrando
cada decisão tomada em tempo de execução.

## Visão geral da solução

O controle de QoE é implementado em duas camadas que atuam juntas:

| Camada | Componente | Função |
|--------|------------|--------|
| Monitoramento | `SDNController` thread (em `run_etapa3.py`) | Lê contadores de bytes do enlace gargalo periodicamente, calcula utilização e decide a ação |
| Decisão | `experiments/qoe_control.py` (funções puras) | Calcula utilização, detecta congestionamento, gera estrutura de decisão |
| Ação SDN | `ovs-ofctl add-flow` em s1 | Instala regra OpenFlow de alta prioridade para o fluxo DASH (TCP porta 8000) |
| Ação de QoS | `tc HTB` em h1-eth0 | Garante banda mínima ao cliente DASH (h2) e limita o tráfego concorrente |

## Lógica de detecção

A cada 2 segundos, o `SDNController` lê o arquivo
`/sys/class/net/s1-eth2/statistics/tx_bytes` para obter os bytes transmitidos
no enlace gargalo s1→s2 (o caminho de todos os downloads de segmentos). A
utilização instantânea é calculada como:

```
util_mbps = (tx_bytes_atual − tx_bytes_anterior) × 8 / (intervalo × 10⁶)
congestionado = util_mbps ≥ 0.8 × capacidade
```

O limiar de 80 % antecipa a saturação antes que a fila do enlace
transborde e provoque perdas ou rebuffering.

## Ações de controle

Quando congestionamento é detectado **e** o modo `com_controle` está ativo,
o `SDNController`:

### 1. Regra OpenFlow via `ovs-ofctl`

```bash
ovs-ofctl add-flow s1 priority=200,ip,nw_proto=6,tp_src=8000,actions=normal
```

Instala dinamicamente uma regra de **alta prioridade** (200 > regras reativas
padrão ≈ 0–100) que casa o tráfego TCP com porta de origem 8000 (segmentos
DASH saindo do servidor). A regra é removida quando o congestionamento cede:

```bash
ovs-ofctl del-flows s1 ip,nw_proto=6,tp_src=8000
```

### 2. Fila de QoS com `tc HTB` em `h1-eth0`

Cria uma hierarquia de filas no host servidor que garante a banda mínima
ao cliente de vídeo **antes** que o tráfego chegue ao gargalo:

```bash
tc qdisc add dev h1-eth0 root handle 1: htb default 12
tc class add dev h1-eth0 parent 1:  classid 1:1  htb rate 10mbit
tc class add dev h1-eth0 parent 1:1 classid 1:11 htb rate 8mbit ceil 10mbit prio 0
tc class add dev h1-eth0 parent 1:1 classid 1:12 htb rate 1mbit  ceil 2mbit  prio 1
tc filter add dev h1-eth0 parent 1: protocol ip prio 1 \
   u32 match ip dst 10.0.0.2/32 flowid 1:11
```

- **Classe 1:11 (DASH → h2)**: 8 Mbps garantidos, pode usar até 10 Mbps;
- **Classe 1:12 (default/cross-traffic)**: 1 Mbps garantido, teto 2 Mbps.

O tráfego concorrente (iperf de h1 para h3/h4) cai na classe default,
protegendo o streaming de h2.

## Logs de decisão em tempo de execução

Cada ciclo de monitoramento gera uma linha em `results/etapa3/decisions.log`:

```
[2026-06-30 10:00:02] dpid=s1 port=2 util=9.412/10.0 Mbps congested=True  action=prioritize_dash
[2026-06-30 10:00:04] dpid=s1 port=2 util=9.380/10.0 Mbps congested=True  action=prioritize_dash
[2026-06-30 10:00:06] dpid=s1 port=2 util=1.205/10.0 Mbps congested=False action=monitor
```

## Metodologia de avaliação

O orquestrador `run_etapa3.py` executa **o mesmo cenário** em dois modos:

| Modo | Controlador | Ação |
|------|-------------|------|
| `sem_controle` | `SDNController` passivo (`mitigate=False`) | só monitora e registra |
| `com_controle` | `SDNController` ativo (`mitigate=True`) | instala regra OF + aplica HTB |

Cenário: enlace gargalo `s1-eth2` limitado a **10 Mbps** (tc tbf) e
**2 fluxos iperf** (h1 → h3/h4) concorrentes ao streaming (h1 → h2).
As métricas de QoE são medidas pelo cliente DASH headless da Etapa 2
(`dash_client.py`).

Resultado esperado:

| Métrica | `sem_controle` | `com_controle` |
|---------|---------------|----------------|
| Bitrate médio | baixo (3–4 Mbps) | alto (≈8 Mbps) |
| Tempo de rebuffering | alto | baixo/zero |
| Vazão de download | limitada | próxima do garantido |

`analyze_etapa3.py` consolida os dois modos em CSV e gera gráficos
comparativos em `results/etapa3/plots/`.

## Como executar

```bash
make video        # gera o conteúdo DASH (se ainda não houver)
make etapa3       # roda sem_controle e com_controle
make analyze3     # CSV + gráficos + ganho percentual no terminal
```

Para um único modo:

```bash
sudo python3 experiments/run_etapa3.py --mode com_controle
```

## Saídas

```text
results/etapa3/summary.json     # bruto consolidado (2 modos)
results/etapa3/summary.csv      # tabela para o relatório
results/etapa3/decisions.log    # log das decisões do controlador (tempo real)
results/etapa3/qoe/*.json       # QoE por modo
results/etapa3/net/*.txt        # ping/iperf por modo
results/etapa3/plots/cmp_*.png  # gráficos comparativos
```

## Testes (TDD)

A lógica de controle — utilização do enlace, detecção de congestionamento,
geração de decisão, construção dos comandos tc HTB e ovs-ofctl, e o cálculo
de ganho da análise — é coberta por **testes que não exigem Mininet nem root**:

```bash
make test   # inclui tests/test_qoe_control.py (22 testes da Etapa 3)
```

## Arquivos da Etapa 3

```text
experiments/qoe_control.py      # lógica pura: detecção, decisão, comandos tc/ovs-ofctl
experiments/run_etapa3.py       # orquestrador: gargalo + SDNController + coleta
experiments/analyze_etapa3.py   # comparação baseline vs controle, gráficos
controller/qoe_guard.py         # versão POX do controlador (uso manual)
tests/test_qoe_control.py       # testes TDD (22 casos)
```
