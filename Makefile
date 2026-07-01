PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: install validate video controller topology capture etapa2 analyze etapa3 analyze3 test clean

install:
	chmod +x install.sh cleanup.sh scripts/*.sh
	./install.sh

validate:
	./scripts/validate_environment.sh

video:
	./scripts/prepare_video.sh

controller:
	./scripts/start_controller.sh

topology:
	./scripts/start_topology.sh

capture:
	sudo ./scripts/capture_traffic.sh s1-eth1

# Etapa 2: roda todos os cenários (degradação + tráfego concorrente) e coleta QoE.
# -B evita criar __pycache__ de propriedade do root (rodamos via sudo).
etapa2:
	sudo python3 -B experiments/run_etapa2.py

# Etapa 2: consolida resultados em CSV e gera os gráficos.
analyze:
	MPLCONFIGDIR=/tmp/qoe_mpl $(PYTHON) experiments/analyze.py

# Etapa 3: controle via SDN. Sobe o POX ext.qoe_guard automaticamente,
# roda os modos sem_controle e com_controle e compara a QoE.
etapa3:
	sudo python3 -B experiments/run_etapa3.py

# Etapa 3: consolida baseline vs. controle em CSV e gera os gráficos.
analyze3:
	MPLCONFIGDIR=/tmp/qoe_mpl $(PYTHON) experiments/analyze_etapa3.py

# Testes (TDD). Não exigem root nem Mininet; os testes de integração com
# ffmpeg são pulados automaticamente se não houver ffmpeg disponível.
test:
	PYTHONPYCACHEPREFIX=/tmp/qoe_pycache MPLCONFIGDIR=/tmp/qoe_mpl $(PYTHON) -m pytest tests/ -v

clean:
	./cleanup.sh
