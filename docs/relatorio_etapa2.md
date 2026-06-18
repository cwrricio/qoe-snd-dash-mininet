# Relatório da Etapa 2 — Indução de Degradação e Caracterização da QoE

## Objetivo

Submeter o ambiente de streaming MPEG-DASH construído na Etapa 1 a **cenários
adversos de rede controlados**, medir o impacto na **Qualidade de Experiência
(QoE)** e **correlacionar** as métricas de rede com as métricas percebidas pela
aplicação. Esta etapa estabelece a *baseline* de degradação que a Etapa 3
(controle via SDN) deverá mitigar.

## Metodologia

### 1. Indução de degradação com `tc` (netem/tbf)

A degradação é aplicada na saída do enlace **servidor → switch** (`h1-eth0`),
que é o gargalo do caminho de download dos segmentos de vídeo. Usamos:

- **`netem`** para atraso, jitter e perda de pacotes;
- **`tbf`** (Token Bucket Filter) para limitação de banda.

Quando há banda + atraso/perda simultâneos, o `netem` é a *qdisc* raiz e o
`tbf` entra como filho (`parent 1:`), conforme implementado em
`experiments/run_etapa2.py` (`apply_impairment`) e disponível também para uso
manual em `scripts/induce_degradation.sh`.

### 2. Tráfego concorrente com `iperf`

No cenário de congestionamento, clientes adicionais (`h3`, `h4`) saturam o
enlace com fluxos `iperf` para o servidor durante toda a reprodução, competindo
por banda com o streaming. Uso manual em `scripts/concurrent_traffic.sh`.

### 3. Medição de QoE com cliente DASH headless

Para obter métricas de QoE **reprodutíveis** (o VLC não expõe essas métricas de
forma confiável em execução headless dentro do Mininet), foi implementado um
cliente DASH próprio (`experiments/dash_client.py`, apenas biblioteca padrão).
Ele:

1. baixa e interpreta o manifesto `output.mpd`;
2. escolhe a qualidade de cada segmento com **ABR baseado em throughput**;
3. simula um **buffer de reprodução**, contabilizando início, paradas e bitrate.

### 4. Automação

`experiments/run_etapa2.py` sobe a topologia, inicia servidor HTTP e `iperf` no
`h1` e executa **todos os cenários em sequência**, aplicando/limpando a
degradação e salvando um JSON por cenário em `results/etapa2/`.
`experiments/analyze.py` consolida tudo em CSV e gera os gráficos.

## Cenários avaliados

| Cenário            | Banda   | Atraso  | Jitter | Perda | Tráfego concorrente |
|--------------------|---------|---------|--------|-------|---------------------|
| `baseline`         | —       | —       | —      | —     | não                 |
| `banda_baixa`      | 3 Mbps  | —       | —      | —     | não                 |
| `atraso_alto`      | —       | 150 ms  | —      | —     | não                 |
| `jitter`           | —       | 50 ms   | 30 ms  | —     | não                 |
| `perda`            | —       | —       | —      | 5 %   | não                 |
| `congestionamento` | 10 Mbps | —       | —      | —     | 2 fluxos iperf      |
| `combinado`        | 3 Mbps  | 100 ms  | —      | 2 %   | não                 |

## Métricas de QoE e justificativa

| Métrica | Significado | Por que importa |
|---------|-------------|-----------------|
| **Tempo de início** (`startup_time_s`) | Tempo até encher o buffer inicial e começar a tocar | Primeiro fator de abandono pelo usuário; sensível a banda e latência |
| **Eventos de rebuffering** (`rebuffer_events`) | Número de paradas por buffer vazio | Interrupções são o fator de QoE mais perceptível e penalizado |
| **Tempo de rebuffering** (`rebuffer_time_s`) | Tempo total congelado | Mede a severidade acumulada das paradas |
| **Bitrate médio** (`avg_bitrate_kbps`) | Qualidade média reproduzida | Reflete nitidez/resolução entregue ao usuário |
| **Trocas de bitrate** (`bitrate_switches`) | Quantidade de mudanças de qualidade | Oscilação excessiva degrada a experiência mesmo sem travar |

Essas métricas seguem os modelos clássicos de QoE para streaming adaptativo
(ITU-T P.1203 e literatura de DASH), em que QoE cresce com o bitrate e cai com
startup e rebuffering.

## Métricas de rede coletadas

- **RTT médio** e **perda** via `ping` (`results/etapa2/net/<cenario>_ping.txt`);
- **Vazão** via `iperf` (`results/etapa2/net/<cenario>_iperf.txt`);
- **Throughput médio** observado pelo próprio cliente DASH durante os downloads.

## Como reproduzir

```bash
# Pré-requisitos da Etapa 1 já instalados e vídeo DASH gerado:
make video

# Roda todos os cenários (sobe a topologia automaticamente):
make etapa2

# Gera CSV e gráficos a partir dos resultados:
make analyze
```

Resultados em:

```text
results/etapa2/summary.json     # bruto consolidado
results/etapa2/summary.csv      # tabela para o relatório
results/etapa2/qoe/*.json       # QoE por cenário
results/etapa2/net/*.txt        # ping/iperf por cenário
results/etapa2/plots/*.png      # gráficos
```

Para um único cenário: `sudo python3 experiments/run_etapa2.py --only banda_baixa`.

> Observação: por padrão usa o controlador de referência embutido do OVS
> (1 comando). Para usar o POX da Etapa 1, rode `make controller` em outro
> terminal e use `sudo python3 experiments/run_etapa2.py --controller remote`.

## Resultados obtidos

Execução realizada no Mininet (controlador OVS, cliente `h2`, vídeo de ~28 s /
14 segmentos de 2 s, escada de bitrate 300 / 800 / 1500 kbps). Dados completos
em `results/etapa2/summary.csv`.

| Cenário | RTT (ms) | Perda ping (%) | Vazão download (Mbps) | Início (s) | Rebuffer (s) | Bitrate médio (kbps) | Trocas |
|---------|---------:|---------------:|----------------------:|-----------:|-------------:|---------------------:|-------:|
| baseline         | 0,13   | 0  | 90,1 | **0,21** | 0 | **1414** | 1 |
| banda_baixa      | 0,17   | 0  | 2,87 | 6,39 | 0 | 1414 | 1 |
| atraso_alto      | 150,5  | 0  | 7,84 | 3,66 | 0 | 1414 | 1 |
| jitter           | 50,5   | 0  | 0,60 | **10,28** | 0 | **300** | 0 |
| perda            | 0,46   | 10 | 24,94 | 1,14 | 0 | 1414 | 1 |
| congestionamento | 19,8   | 0  | 8,98 | 2,17 | 0 | 1414 | 1 |
| combinado        | 102,9  | 10 | 1,54 | 5,56 | 0 | 1064 | **9** |

> A coluna "Vazão download" é a vazão **servidor → cliente** medida pelo próprio
> cliente DASH (caminho do streaming). O `iperf` da coleta mede o **uplink**
> (cliente → servidor), que não é shapeado nos cenários de banda; por isso ele
> aparece alto (~95 Mbps) no `banda_baixa` e é apresentado apenas como
> referência em `summary.csv` (coluna `throughput_mbps`).

Gráficos em `results/etapa2/plots/`: `qoe_startup.png`, `qoe_rebuffer.png`,
`qoe_bitrate.png`, `corr_throughput_bitrate.png`, `corr_loss_rebuffer.png`,
`corr_rtt_startup.png`.

## Análise da relação rede × QoE

**Como a degradação se manifestou.** Em todos os cenários **não houve
rebuffering** (0 paradas). A degradação apareceu no **tempo de início** e no
**bitrate**. Isso é coerente com o comportamento de um player adaptativo: ele
**sacrifica qualidade para preservar a continuidade**, e como a pior vazão
observada (0,60 Mbps, no `jitter`) ainda supera a menor representação
(0,30 Mbps), a reprodução nunca travou. Tempo de início e bitrate foram, então,
as métricas discriminantes.

- **`jitter` (pior caso de QoE)**: vazão de download desabou para **0,60 Mbps** e
  o cliente ficou preso na menor qualidade (**300 kbps**), com **início de
  10,3 s**. O jitter penaliza o TCP (reordenação e retransmissões espúrias,
  inflação do RTO) muito mais do que um atraso fixo equivalente.
- **`banda_baixa` (3 Mbps)**: o **início saltou para 6,4 s**, mas o **bitrate se
  manteve no topo (1414 kbps)** — porque a maior representação (1,5 Mbps) cabe
  em 3 Mbps. Mostra que o impacto da limitação de banda depende da relação entre
  o limite e a escada de bitrate do conteúdo.
- **`atraso_alto` (150 ms)**: **início de 3,7 s** (o RTT alto retarda o
  *slow-start* do TCP e o enchimento do buffer inicial); bitrate intacto, pois a
  banda era folgada.
- **`perda` (5%)**: impacto modesto (**início 1,1 s**); a perda reduziu a vazão,
  mas, no clipe curto, ainda sobrou banda para a melhor qualidade. O `ping`
  registrou ~10% por ser bidirecional/amostra pequena.
- **`congestionamento`**: os fluxos `iperf` concorrentes reduziram a banda
  disponível (uplink medido em 2,5 Mbps), elevando o início para 2,2 s; o vídeo
  ainda obteve qualidade máxima na vazão de download residual.
- **`combinado` (3 Mbps + 100 ms + 2%)**: caso realista mais severo —
  **início de 5,6 s**, bitrate médio caindo para **1064 kbps** e **9 trocas de
  qualidade** (instabilidade/oscilação do ABR).

**Correlações observadas (gráficos):**

- **Vazão de download × bitrate** (`corr_throughput_bitrate.png`): relação
  positiva — abaixo de ~1,5 Mbps de download o ABR é forçado a recuar (jitter e
  combinado), enquanto ≥ 2,8 Mbps já sustentam a qualidade máxima.
- **RTT × tempo de início** (`corr_rtt_startup.png`): relação positiva — maior
  latência ⇒ maior tempo de início (visível em `atraso_alto` e `combinado`).
- **Perda × rebuffering** (`corr_loss_rebuffer.png`): **inconclusiva neste
  experimento**, pois não houve rebuffering em nenhum cenário; o efeito da perda
  apareceu na vazão e, indiretamente, no início/bitrate.

**Justificativa das métricas (revisitada com os dados):** o tempo de início e o
bitrate foram suficientes para distinguir claramente todos os cenários adversos
do baseline; o rebuffering, embora seja a métrica de QoE mais crítica, não foi
acionado por causa da proteção do ABR — o que reforça a importância de medir as
três métricas em conjunto.


## Conclusão

A Etapa 2 forneceu **evidência controlada e reprodutível** de degradação de QoE
sob condições adversas. Os dados mostram que **jitter** e **banda baixa** foram
os fatores que mais elevaram o **tempo de início** (10,3 s e 6,4 s vs. 0,21 s do
baseline), que o **jitter** foi o único a derrubar o **bitrate** ao mínimo
(300 kbps) e que o cenário **combinado** gerou a maior **instabilidade** de
qualidade (9 trocas). Em nenhum caso houve rebuffering, pois o ABR trocou
qualidade por continuidade — resultado que evidencia a interdependência entre as
três métricas de QoE escolhidas.

Esses números servem de **baseline** para a Etapa 3: o mecanismo de controle via
SDN deverá, sobretudo, **reduzir o tempo de início e estabilizar/elevar o
bitrate** nos cenários de banda baixa, jitter e congestionamento — priorizando
ou protegendo o fluxo de vídeo frente ao tráfego concorrente.
