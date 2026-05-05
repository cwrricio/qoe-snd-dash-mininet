.PHONY: install validate video controller topology capture clean

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

clean:
	./cleanup.sh
