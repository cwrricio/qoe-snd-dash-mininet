#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import Topo
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


class DashTopo(Topo):
    def build(self):
        server = self.addHost("h1", ip="10.0.0.1/24")
        client1 = self.addHost("h2", ip="10.0.0.2/24")
        client2 = self.addHost("h3", ip="10.0.0.3/24")
        client3 = self.addHost("h4", ip="10.0.0.4/24")

        s1 = self.addSwitch("s1")
        s2 = self.addSwitch("s2")

        self.addLink(server, s1, cls=TCLink, bw=100)
        self.addLink(s1, s2, cls=TCLink, bw=100)
        self.addLink(client1, s2, cls=TCLink, bw=100)
        self.addLink(client2, s2, cls=TCLink, bw=100)
        self.addLink(client3, s2, cls=TCLink, bw=100)


def run():
    topo = DashTopo()

    net = Mininet(
        topo=topo,
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )

    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6633
    )

    net.start()

    info("\n[INFO] Testando conectividade inicial...\n")
    net.pingAll()

    info("\n[INFO] Iniciando servidor HTTP no h1...\n")
    h1 = net.get("h1")
    h1.cmd("cd media/dash && python3 -m http.server 8000 > /tmp/http_dash.log 2>&1 &")

    info("\n[INFO] Servidor DASH disponível em:\n")
    info("       http://10.0.0.1:8000/output.mpd\n")

    info("\n[INFO] Use no VLC dos clientes:\n")
    info("       vlc http://10.0.0.1:8000/output.mpd\n")

    CLI(net)

    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()