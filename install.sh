#!/bin/bash

set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive

echo "[INFO] Iniciando instalação do ambiente da Etapa 1..."

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$PROJECT_DIR/tools"
POX_DIR="$TOOLS_DIR/pox"

echo "[0/7] Corrigindo chave GPG do repositório HashiCorp, se existir..."

if [ -f /etc/apt/sources.list.d/hashicorp.list ]; then
    sudo apt-get install -y gpg wget lsb-release ca-certificates curl

    echo "[INFO] Removendo keyring antigo da HashiCorp para evitar pergunta de sobrescrita..."
    sudo rm -f /usr/share/keyrings/hashicorp-archive-keyring.gpg

    echo "[INFO] Baixando novamente a chave GPG da HashiCorp..."
    curl -fsSL https://apt.releases.hashicorp.com/gpg | \
        sudo gpg --dearmor --batch --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

    UBUNTU_CODENAME="$(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs)"

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${UBUNTU_CODENAME} main" | \
        sudo tee /etc/apt/sources.list.d/hashicorp.list > /dev/null

    echo "[OK] Repositório HashiCorp ajustado sem interação manual."
else
    echo "[INFO] Repositório HashiCorp não encontrado. Pulando correção."
fi

echo "[1/7] Atualizando pacotes..."
sudo apt-get update

echo "[2/7] Instalando dependências do sistema..."
sudo apt-get install -y \
    git \
    mininet \
    openvswitch-switch \
    openvswitch-testcontroller \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    vlc \
    iperf \
    iperf3 \
    tcpdump \
    net-tools \
    curl \
    make \
    python3-matplotlib \
    python3-pytest

echo "[3/7] Configurando Open vSwitch..."
sudo systemctl enable openvswitch-switch
sudo systemctl restart openvswitch-switch

echo "[4/7] Preparando diretório de ferramentas..."
mkdir -p "$TOOLS_DIR"

echo "[5/7] Instalando/atualizando controlador POX..."

if [ ! -d "$POX_DIR" ]; then
    git clone https://github.com/noxrepo/pox.git "$POX_DIR"
    echo "[OK] POX clonado em $POX_DIR"
else
    echo "[INFO] POX já existe. Atualizando..."
    git -C "$POX_DIR" pull --ff-only || true
fi

echo "[6/7] Validando controlador POX..."

if [ -f "$POX_DIR/pox.py" ]; then
    echo "[OK] pox.py encontrado em $POX_DIR/pox.py"
else
    echo "[ERRO] pox.py não encontrado."
    exit 1
fi

# Instala o app de controle da Etapa 3 (versionado em controller/) no ext do POX.
if [ -f "$PROJECT_DIR/controller/qoe_guard.py" ]; then
    mkdir -p "$POX_DIR/ext"
    cp "$PROJECT_DIR/controller/qoe_guard.py" "$POX_DIR/ext/qoe_guard.py"
    echo "[OK] App de controle (ext.qoe_guard) instalado no POX."
fi

echo "[7/7] Limpando instâncias antigas do Mininet..."
sudo mn -c || true

echo ""
echo "[OK] Instalação concluída."
echo ""
echo "Próximos passos:"
echo "  make validate"
echo "  make video"
echo "  make controller"
echo "  make topology"
