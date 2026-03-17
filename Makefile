.PHONY: up down restart logs clean-jupyter

up:
	./start_dslab.sh

down:
	podman-compose down

logs:
	podman-compose logs -f

clean-jupyter:
	@echo "🧹 Nettoyage des sessions Jupyter orphelines..."
	podman rm -f $$(podman ps -aq --filter name=jupyter-) 2>/dev/null || true

restart: down clean-jupyter
	@echo "🔄 Redémarrage de l'infrastructure..."
	./start_dslab.sh

logs:
	podman-compose logs -f