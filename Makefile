.PHONY: up down restart logs

up:
	./start_dslab.sh

down:
	podman-compose down

logs:
	podman-compose logs -f

restart:
	podman-compose down && ./start_dslab.sh