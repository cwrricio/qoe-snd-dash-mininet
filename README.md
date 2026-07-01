# QoE SDN DASH Mininet

Entregas das **Etapas 1, 2 e 3** do Trabalho Final de Programabilidade de Infraestruturas de Rede.

Este repositório monta um ambiente experimental para **streaming adaptativo (MPEG-DASH)** sobre uma rede **SDN** emulada no **Mininet**, controlada por um controlador **POX** via **OpenFlow**.

## Sumário

- [Objetivo](#objetivo)
- [Topologia](#topologia)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Ambiente recomendado](#ambiente-recomendado)
- [Instalação](#instalação)
- [Validar o ambiente](#validar-o-ambiente)
- [Preparar o vídeo (MPEG-DASH)](#preparar-o-vídeo-mpeg-dash)
- [Controlador SDN utilizado](#controlador-sdn-utilizado)
- [Executar (controlador + topologia)](#executar-controlador--topologia)
- [Testes, VLC e métricas](#testes-vlc-e-métricas)
- [Captura de tráfego](#captura-de-tráfego)
- [Etapa 2 — Indução de degradação e caracterização da QoE](#etapa-2--indução-de-degradação-e-caracterização-da-qoe)
- [Etapa 3 — Controle via SDN (mitigação de degradação)](#etapa-3--controle-via-sdn-mitigação-de-degradação)
- [Resultados obtidos](#resultados-obtidos)
- [Encerrar e limpar](#encerrar-e-limpar)
- [Ordem resumida](#ordem-resumida)
- [Evidências para a entrega](#evidências-para-a-entrega)
- [Notas e troubleshooting](#notas-e-troubleshooting)

## Objetivo

Na Etapa 1, o foco é:

- instalar e configurar o ambiente;
- criar uma topologia com servidor, clientes e switches OpenFlow;
- integrar a topologia com um controlador SDN;
- gerar e servir vídeo MPEG-DASH;
- reproduzir o vídeo usando VLC;
- coletar métricas iniciais de rede com `ping` e `iperf`;
- capturar tráfego com `tcpdump` (e analisar no Wireshark).

## Topologia

Elementos da topologia:

- servidor de vídeo: `h1`
- clientes: `h2`, `h3`, `h4`
- switches OpenFlow: `s1`, `s2`
- controlador SDN (remoto): `c0`

Diagrama (lógico):

```text
h1 --- s1 --- s2 --- h2
              |
              +---- h3
              |
              +---- h4
```

O host `h1` executa o servidor HTTP com o conteúdo MPEG-DASH. Os hosts `h2`, `h3` e `h4` acessam o vídeo.

## Estrutura do projeto

```text
.
├── docs/
│   ├── README_VM.md
│   ├── relatorio_etapa1.md
│   ├── relatorio_etapa2.md
│   └── relatorio_etapa3.md
├── experiments/
│   ├── dash_client.py
│   ├── netimpair.py
│   ├── qoe_control.py
│   ├── run_etapa2.py
│   ├── run_etapa3.py
│   ├── analyze.py
│   └── analyze_etapa3.py
├── media/
│   ├── input.mp4
│   └── dash/
├── results/
│   ├── iperf/
│   ├── pcap/
│   ├── ping/
│   └── etapa2/
├── scripts/
│   ├── capture_traffic.sh
│   ├── concurrent_traffic.sh
│   ├── induce_degradation.sh
│   ├── prepare_video.sh
│   ├── run_metrics.sh
│   ├── start_controller.sh
│   ├── start_controller_qoe.sh
│   ├── start_topology.sh
│   └── validate_environment.sh
├── tests/
│   ├── test_dash_client.py
│   ├── test_netimpair.py
│   ├── test_qoe_control.py
│   ├── test_analyze.py
│   └── test_integration_streaming.py
├── controller/
│   └── qoe_guard.py         # app POX da Etapa 3 (copiado p/ tools/pox/ext)
├── tools/
│   └── pox/                 # baixado pelo install.sh (ignorado no git)
├── topology/
│   └── topo_dash.py
├── cleanup.sh
├── install.sh
├── Makefile
├── README.md
└── requirements.txt
```

## Ambiente recomendado

Este projeto foi pensado para execução em Linux.

- Ubuntu 22.04 LTS
- 2 CPUs
- 4 GB de RAM
- 25 GB de disco

Para execução em VM, veja `docs/README_VM.md`.

## Instalação

Na raiz do projeto:

```bash
cd qoe-sdn-dash-mininet
chmod +x install.sh cleanup.sh scripts/*.sh
make install
```

O `make install` instala dependências do sistema (Mininet, Open vSwitch, FFmpeg, VLC, iperf, tcpdump, etc.) e baixa o POX em `tools/pox/`.

## Validar o ambiente

```bash
make validate
```

Saída esperada (exemplo):

```text
[INFO] Validando ambiente...
[OK] git instalado
[OK] Mininet instalado
[OK] Open vSwitch instalado
[OK] Python 3 instalado
[OK] FFmpeg instalado
[OK] VLC instalado
[OK] iperf instalado
[OK] iperf3 instalado
[OK] tcpdump instalado
[OK] make instalado
[OK] Controlador POX encontrado em tools/pox
[OK] Ambiente validado com sucesso.
```

## Preparar o vídeo (MPEG-DASH)

Coloque um vídeo chamado `input.mp4` em:

```text
media/input.mp4
```

Depois, gere o conteúdo DASH:

```bash
make video
```

Arquivos gerados em:

```text
media/dash/
```

Manifesto principal:

```text
media/dash/output.mpd
```

## Controlador SDN utilizado

O controlador SDN utilizado nesta etapa é o **POX**, executando a aplicação:

```text
forwarding.l2_learning
```

O enunciado da Etapa 1 solicita a integração com um controlador SDN (Ryu costuma ser citado como exemplo). Para garantir reprodutibilidade com Mininet/OpenFlow, foi adotado o POX.

O POX é instalado automaticamente pelo `install.sh` em:

```text
tools/pox/
```

## Executar (controlador + topologia)

1) Em um terminal, execute o controlador:

```bash
make controller
```

Deixe esse terminal aberto.

2) Em outro terminal, inicie a topologia:

```bash
make topology
```

Ao final, você entra no prompt interativo do Mininet:

```text
mininet>
```

## Testes, VLC e métricas

### Verificar nós e links

No prompt do Mininet:

```bash
nodes
net
```

### Testar conectividade

```bash
pingall
```

### Testar o servidor DASH

O script da topologia inicia um servidor HTTP no host `h1`.

URL do manifesto:

```text
http://10.0.0.1:8000/output.mpd
```

Teste via `curl`:

```bash
h2 curl http://10.0.0.1:8000/output.mpd
```

Se aparecer XML (`<MPD ...>`), o manifesto está acessível.

### Reprodução do vídeo no VLC

Os comandos executados dentro dos hosts do Mininet frequentemente rodam como **root**. O VLC pode recusar execução como root, exibindo algo como:

```text
VLC is not supposed to be run as root.
```

Se isso acontecer, execute o VLC como o usuário normal do sistema (substitua `<usuario_linux>`):

```bash
h2 sudo -u <usuario_linux> vlc http://10.0.0.1:8000/output.mpd &
```

Se o VLC rodar normalmente no seu ambiente sem essa restrição, o comando direto também funciona:

```bash
h2 vlc http://10.0.0.1:8000/output.mpd
```

### Medir vazão com iperf

No Mininet, inicie o servidor `iperf` no `h1`:

```bash
h1 iperf -s > results/iperf/server_h1.txt &
```

Execute os testes a partir dos clientes (salvando os resultados):

```bash
h2 iperf -c 10.0.0.1 -t 10 > results/iperf/h2_to_h1.txt
h3 iperf -c 10.0.0.1 -t 10 > results/iperf/h3_to_h1.txt
h4 iperf -c 10.0.0.1 -t 10 > results/iperf/h4_to_h1.txt
```

### Medir latência/perda com ping

```bash
h2 ping -c 10 10.0.0.1 > results/ping/h2_to_h1.txt
h3 ping -c 10 10.0.0.1 > results/ping/h3_to_h1.txt
h4 ping -c 10 10.0.0.1 > results/ping/h4_to_h1.txt
```

## Captura de tráfego

A captura do tráfego do streaming pode ser iniciada com:

```bash
make capture
```

Esse comando executa o script:

```text
scripts/capture_traffic.sh
```

Por padrão, a captura é feita na interface `s1-eth1`, associada ao enlace entre o servidor `h1` e o switch `s1`.

Enquanto a captura estiver ativa, reproduza o vídeo novamente em um cliente (exemplo):

```bash
h2 sudo -u <usuario_linux> vlc http://10.0.0.1:8000/output.mpd &
```

Para encerrar a captura: `CTRL + C`.

O arquivo `.pcap` é salvo em:

```text
results/pcap/
```

Esse arquivo pode ser aberto no Wireshark. Filtros úteis:

```text
http
tcp.port == 8000
icmp
```

## Etapa 2 — Indução de degradação e caracterização da QoE

A Etapa 2 submete o ambiente a cenários adversos de rede, mede o impacto na
**QoE** do streaming e correlaciona métricas de rede com métricas de QoE.
Detalhes e metodologia em [`docs/relatorio_etapa2.md`](docs/relatorio_etapa2.md).

### Componentes

```text
experiments/
├── dash_client.py    # cliente DASH headless que mede QoE (só stdlib)
├── run_etapa2.py     # orquestra todos os cenários e coleta resultados
└── analyze.py        # consolida CSV e gera gráficos
scripts/
├── induce_degradation.sh  # aplica tc netem/tbf manualmente (uso no CLI)
└── concurrent_traffic.sh  # gera tráfego concorrente iperf (uso no CLI)
```

### Cenários

`baseline`, `banda_baixa` (3 Mbps), `atraso_alto` (150 ms), `jitter` (50 ms ±
30 ms), `perda` (5%), `congestionamento` (10 Mbps + 2 fluxos iperf) e
`combinado` (3 Mbps + 100 ms + 2% perda).

### Métricas de QoE

Tempo de início, eventos e tempo de rebuffering, bitrate médio e trocas de
bitrate — medidas pelo cliente DASH, que interpreta o `.mpd`, faz ABR por
throughput e simula um buffer de reprodução.

### Executar

```bash
make video      # gera o conteúdo DASH (se ainda não gerou)
make etapa2     # roda todos os cenários (sobe a topologia automaticamente)
make analyze    # gera results/etapa2/summary.csv e os gráficos em plots/
```

Para um cenário específico:

```bash
sudo python3 experiments/run_etapa2.py --only banda_baixa
```

> Por padrão usa o controlador de referência do OVS (1 comando). Para usar o
> POX da Etapa 1: `make controller` em outro terminal e
> `sudo python3 experiments/run_etapa2.py --controller remote`.

### Saídas

```text
results/etapa2/summary.json   # resultado bruto consolidado
results/etapa2/summary.csv    # tabela para o relatório
results/etapa2/qoe/*.json     # QoE por cenário
results/etapa2/net/*.txt      # ping/iperf por cenário
results/etapa2/plots/*.png    # gráficos comparativos e de correlação
```

### Testes (TDD)

A lógica da Etapa 2 (cliente DASH, construção dos comandos `tc`, parsing de
`ping`/`iperf`, pipeline de análise) é coberta por testes automatizados que
**não exigem root nem Mininet**:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
make test
```

São 36 testes, incluindo testes de **integração end-to-end** que geram DASH
real com ffmpeg, sobem um servidor HTTP local (com banda limitada) e validam a
QoE medida — pulados automaticamente se não houver ffmpeg disponível.

### Uso manual da degradação (dentro do CLI do Mininet)

```bash
mininet> h1 bash scripts/induce_degradation.sh h1-eth0 --bw 3 --delay 100ms --loss 2
mininet> h1 bash scripts/induce_degradation.sh h1-eth0 --clear
mininet> h3 bash scripts/concurrent_traffic.sh 10.0.0.1 60 &
```

## Etapa 3 — Controle via SDN (mitigação de degradação)

A Etapa 3 implementa no controlador SDN a **detecção de degradação** e um
**mecanismo de mitigação** que melhora a QoE sob congestionamento, programando
**regras OpenFlow dinamicamente** e registrando as decisões em tempo de
execução. Metodologia completa em
[`docs/relatorio_etapa3.md`](docs/relatorio_etapa3.md).

### Como funciona

O alvo `make etapa3` inicia automaticamente o controlador POX
`qoe_guard` e conecta a topologia Mininet a ele via `RemoteController`.
O POX coleta estatísticas OpenFlow da porta gargalo de `s1` a cada 2 s.
Quando a utilização ultrapassa 80 % da capacidade:

1. **Regra OpenFlow** instalada dinamicamente pelo POX:
   alta prioridade para o tráfego DASH (TCP porta 8000);
2. **tc HTB** aplicado pelo orquestrador em `h1-eth0`: garante 8 Mbps ao
   cliente de vídeo (h2) e limita o tráfego concorrente a 2 Mbps total.

No modo `sem_controle`, o mesmo POX registra as leituras sem agir —
comparação justa com e sem controle. A lógica de decisão é pura e testável
(`experiments/qoe_control.py`). O HTB fica no orquestrador porque é uma fila
Linux do host servidor, fora da superfície configurável por OpenFlow.

O app POX também fica disponível para execução manual via
`scripts/start_controller_qoe.sh`; o caminho reproduzível da entrega é
`make etapa3`.

### Componentes

```text
experiments/
├── qoe_control.py      # lógica pura: detecção, decisão, comandos tc/ovs-ofctl
├── run_etapa3.py       # sobe POX e orquestra sem_controle vs com_controle
└── analyze_etapa3.py   # consolida CSV e gera gráficos comparativos
controller/
└── qoe_guard.py        # app POX usado automaticamente no make etapa3
```

### Executar

```bash
make video      # gera o conteúdo DASH (se ainda não houver)
make etapa3     # roda sem_controle e com_controle
make analyze3   # gera results/etapa3/summary.csv e os gráficos comparativos
make test       # valida a lógica pura e a integridade do controlador POX
```

Para um único modo:

```bash
sudo python3 experiments/run_etapa3.py --mode com_controle
```

### Saídas

```text
results/etapa3/summary.json     # bruto consolidado (2 modos)
results/etapa3/summary.csv      # tabela para o relatório
results/etapa3/decisions.log    # log das decisões do POX (tempo real)
results/etapa3/qos_decisions.log # log da aplicação de HTB no host servidor
results/etapa3/pox_*.log        # stdout/stderr do POX por modo
results/etapa3/qoe/*.json       # QoE por modo
results/etapa3/net/*.txt        # ping/iperf por modo
results/etapa3/plots/cmp_*.png  # gráficos comparativos (sem vs com controle)
```

### Testes

A lógica da Etapa 3 é coberta por testes que **não exigem Mininet nem root**
(`tests/test_qoe_control.py`), incluídos em `make test`.

Se estiver fora da VM preparada por `make install`, crie um ambiente local:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make test
```

## Resultados obtidos

Durante a execução da Etapa 1, as evidências e resultados **podem** ser organizados nos diretórios:

```text
results/ping/
results/iperf/
results/pcap/
```

- Conectividade: validada com `pingall` (idealmente 0% dropped).
- Latência/perda: arquivos gerados com `ping` (ex.: `results/ping/h2_to_h1.txt`).
- Vazão: arquivos gerados com `iperf` (ex.: `results/iperf/h2_to_h1.txt`).
- Tráfego: `.pcap` gerado em `results/pcap/`.

## Encerrar e limpar

Saia do Mininet:

```bash
exit
```

Depois limpe o ambiente:

```bash
make clean
```

## Ordem resumida

Terminal 1:

```bash
make controller
```

Terminal 2:

```bash
make topology
```

Dentro do Mininet:

```bash
nodes
net
pingall
h2 curl http://10.0.0.1:8000/output.mpd
h2 sudo -u <usuario_linux> vlc http://10.0.0.1:8000/output.mpd &
h1 iperf -s > results/iperf/server_h1.txt &
h2 iperf -c 10.0.0.1 -t 10 > results/iperf/h2_to_h1.txt
```

Terminal 3:

```bash
make capture
```

## Notas e troubleshooting

### Importante: rode a topologia a partir da raiz do projeto

O servidor HTTP do DASH é iniciado a partir do diretório `media/dash`. Por isso, execute a topologia pela raiz:

```bash
cd qoe-sdn-dash-mininet
make topology
```

Evite executar diretamente o script assim:

```bash
cd topology
sudo python3 topo_dash.py
```

Caso contrário, o Mininet pode não encontrar `media/dash`.

### Permissão negada no `make analyze` ou nos testes

Como o `make etapa2` roda via `sudo`, arquivos podem ser criados como **root**.
O orquestrador já devolve a posse de `results/` ao seu usuário ao final, e usa
`python3 -B` para não criar `__pycache__` como root. Se você rodou uma versão
anterior e ainda houver arquivos do root, limpe uma única vez:

```bash
sudo chown -R $USER:$USER results/
sudo rm -rf experiments/__pycache__ topology/__pycache__
```
