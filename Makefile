.PHONY: dev backend frontend install install-backend install-frontend clean

# Config
VENV := venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
BACKEND_PORT := 8000
FRONTEND_PORT := 5173

# Run backend + frontend together. Ctrl-C stops both.
dev:
	@echo "Starting backend (:$(BACKEND_PORT)) and frontend (:$(FRONTEND_PORT))..."
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

backend:
	$(UVICORN) app.main:app --reload --port $(BACKEND_PORT)

frontend:
	cd frontend && npm run dev -- --port $(FRONTEND_PORT)

# One-time setup
install: install-backend install-frontend

install-backend:
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt

install-frontend:
	cd frontend && npm install

clean:
	rm -rf $(VENV) frontend/node_modules
