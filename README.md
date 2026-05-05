# QoE SDN DASH Mininet

Entrega da **Etapa 1** do Trabalho Final de Programabilidade de Infraestruturas de Rede.

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
│   └── README_VM.md
├── media/
│   ├── input.mp4
│   └── dash/
├── results/
│   ├── iperf/
│   ├── pcap/
│   └── ping/
├── scripts/
│   ├── capture_traffic.sh
│   ├── prepare_video.sh
│   ├── run_metrics.sh
│   ├── start_controller.sh
│   ├── start_topology.sh
│   └── validate_environment.sh
├── tools/
│   └── pox/
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

## Evidências para a entrega

Recomenda-se registrar:

- print do `make validate`;
- print do controlador POX em execução;
- print da topologia Mininet iniciada;
- print dos comandos `nodes`, `net`, `pingall`;
- print do `curl` acessando `output.mpd`;
- print do VLC reproduzindo o vídeo;
- print dos testes `ping` e `iperf` (ou os arquivos salvos em `results/`);
- arquivo `.pcap` gerado em `results/pcap/`.

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
