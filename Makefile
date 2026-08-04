.PHONY: seed-demo

# Seeds local development demo data (organization, one user per Community
# role, three projects). Development-only — refuses to run under production
# settings. Requires the stack to be running (`docker compose up`).
seed-demo:
	docker compose exec backend python manage.py seed_demo
