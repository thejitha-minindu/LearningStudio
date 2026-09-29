.PHONY: dev dev-build prod stop logs

dev:
	docker compose -f compose.yaml -f compose.dev.yaml up

dev-build:
	docker compose -f compose.yaml -f compose.dev.yaml up --build

prod:
	docker compose -f compose.yaml -f compose.prod.yaml up -d --build

stop:
	docker compose down

logs:
	docker compose logs -f
