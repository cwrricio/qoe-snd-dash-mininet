# Relatório da Etapa 1

## Objetivo

Construir um ambiente experimental **funcional e reproduzível** para streaming de vídeo **MPEG-DASH** em uma rede **SDN** emulada com **Mininet**.

## Ambiente

Execução em Linux, utilizando:

- Mininet
- Open vSwitch
- POX
- FFmpeg
- VLC
- iperf
- tcpdump

## Topologia

Elementos:

- `h1`: servidor de vídeo
- `h2`, `h3`, `h4`: clientes
- `s1`, `s2`: switches OpenFlow
- `c0`: controlador remoto

Diagrama (lógico):

```text
h1 --- s1 --- s2 --- h2
              |
              +---- h3
              |
              +---- h4
```

## Controlador SDN

Foi utilizado o **POX** com a aplicação:

```text
forwarding.l2_learning
```

Essa aplicação implementa o comportamento de **switch L2 com aprendizagem (learning switch)**, permitindo a comunicação automática entre os hosts.

## Streaming MPEG-DASH

O vídeo original foi fornecido em:

```text
media/input.mp4
```

O conteúdo DASH foi gerado com FFmpeg, produzindo o manifesto:

```text
media/dash/output.mpd
```

O servidor HTTP foi iniciado no host `h1`, disponibilizando o conteúdo em:

```text
http://10.0.0.1:8000/output.mpd
```

Validação no cliente `h2`:

```bash
h2 curl http://10.0.0.1:8000/output.mpd
```

Reprodução no VLC (observação: dentro do Mininet, comandos podem rodar como root):

```bash
h2 sudo -u <usuario_linux> vlc http://10.0.0.1:8000/output.mpd &
```

## Métricas coletadas

Foram coletadas métricas de **latência/perda** e **vazão**.

- Resultados de `ping` em:

```text
results/ping/
```

- Resultados de `iperf` em:

```text
results/iperf/
```

- Capturas de tráfego (`.pcap`) em:

```text
results/pcap/
```

## Resultado

A topologia foi executada com sucesso.

- `pingall` obteve **0% dropped**, indicando conectividade entre os hosts.
- O manifesto DASH foi acessado pelos clientes via `curl`.
- O vídeo foi reproduzido via VLC, validando o streaming MPEG-DASH.

## Reprodução (resumo)

Sequência típica para repetir o experimento:

```bash
make install
make validate
make video
make controller
make topology
```

No prompt do Mininet:

```bash
pingall
h2 curl http://10.0.0.1:8000/output.mpd
h2 sudo -u <usuario_linux> vlc http://10.0.0.1:8000/output.mpd &
```