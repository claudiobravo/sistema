.PHONY: arriba abajo logs qr estado grupos webhook prueba test

arriba:        ## levanta la pila
	docker compose up -d --build

abajo:
	docker compose down

logs:
	docker compose logs -f bot

qr:
	docker compose exec bot python -m tools.gestion qr

estado:
	docker compose exec bot python -m tools.gestion estado

grupos:
	docker compose exec bot python -m tools.gestion grupos

webhook:
	docker compose exec bot python -m tools.gestion webhook

prueba:
	docker compose exec bot python -m tools.gestion probar

test:
	python -m pytest
