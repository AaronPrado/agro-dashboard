# Makefile — atajos sobre docker compose. Las recetas usan TABULADOR, no espacios.
COMPOSE := docker compose
SERVICE := web
FRONTEND := frontend

.DEFAULT_GOAL := help
.PHONY: help build up up-d down logs migrate makemigrations shell lint format test seed reseed lint-fix front-install front-dev front-lint front-build

help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

build:  ## Construye la imagen del backend
	$(COMPOSE) build

up:  ## Levanta el stack en primer plano (Ctrl+C para parar)
	$(COMPOSE) up

up-d:  ## Levanta el stack en segundo plano
	$(COMPOSE) up -d

down:  ## Para el stack y elimina los contenedores
	$(COMPOSE) down

logs:  ## Sigue los logs del backend
	$(COMPOSE) logs -f $(SERVICE)

migrate:  ## Aplica migraciones
	$(COMPOSE) run --rm $(SERVICE) python manage.py migrate

makemigrations:  ## Genera migraciones a partir de los modelos y las formatea
	$(COMPOSE) run --rm $(SERVICE) python manage.py makemigrations
	$(MAKE) format

shell:  ## Abre la shell de Django
	$(COMPOSE) run --rm $(SERVICE) python manage.py shell

lint:  ## Lint con ruff (no necesita base de datos)
	$(COMPOSE) run --rm --no-deps $(SERVICE) ruff check .

format:  ## Formatea el código con ruff
	$(COMPOSE) run --rm --no-deps $(SERVICE) ruff format .

lint-fix:  ## Corrige lo que ruff puede arreglar solo (incluye el orden de imports)
	$(COMPOSE) run --rm --no-deps $(SERVICE) ruff check --fix .
	$(MAKE) format

test:  ## Ejecuta la batería de tests con pytest
	$(COMPOSE) run --rm $(SERVICE) pytest

seed:  ## Puebla la BD con datos mockeados (disponible desde la Sesión 3)
	$(COMPOSE) run --rm $(SERVICE) python manage.py seed

reseed:  ## Vacía y vuelve a sembrar (obligatorio tras tocar el generador)
	$(COMPOSE) run --rm $(SERVICE) python manage.py seed --clear

front-install:  ## Instala las dependencias del cliente (host, no Docker)
	cd $(FRONTEND) && npm install

front-dev:  ## Levanta el dev server de Vite (host; reenvía /api al backend)
	cd $(FRONTEND) && npm run dev

front-lint:  ## Lint del cliente con ESLint (host)
	cd $(FRONTEND) && npm run lint

front-build:  ## Compila el cliente para producción (host)
	cd $(FRONTEND) && npm run build
