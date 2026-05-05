# Ambiente de Máquina Virtual (VM)

Este projeto pode ser executado diretamente em um sistema Linux ou dentro de uma máquina virtual.

## Sistema recomendado

- Ubuntu 22.04 LTS
- 2 CPUs
- 4 GB de RAM
- 25 GB de disco

## Virtualizadores sugeridos

- VirtualBox
- VMware Workstation
- VMware Player

## Configuração de rede

- A VM pode usar modo **NAT** para instalar pacotes.
- O Mininet cria interfaces virtuais internamente; para esta etapa, normalmente **não é necessário** adicionar múltiplas placas de rede na VM.

## Observações

- Recomenda-se executar os comandos com um usuário que tenha permissão de `sudo`.
- Antes de cada nova execução, recomenda-se limpar o ambiente com:

```bash
make clean
```

