# Agent Adda — installer Makefile.
# Convenience targets that wrap install.sh / setup_wizard.py / doctor.py.
#
# Usage (from project root):
#   make -C installer help
#   make -C installer install
#   make -C installer doctor
#   make -C installer agent
#
# Designed to be safe to re-run; every target is idempotent.

ROOT      := $(abspath $(dir $(MAKEFILE_LIST))/..)
VENV      := $(ROOT)/.venv
PY        := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
INSTALLER := $(ROOT)/installer

# detect OS for service install hint
UNAME_S := $(shell uname -s)

.PHONY: help install install-system install-deps install-dev-deps wizard doctor agent refresh \
        services-install services-uninstall app app-install package package-dry \
        data-seed data-seed-schema data-restore test clean uninstall

help:
	@echo ""
	@echo "Agent Adda — installer targets"
	@echo "  make install            ./install.sh + setup wizard (full first-time setup)"
	@echo "  make install-system     install.sh only (system bootstrap, no wizard)"
	@echo "  make install-deps       reinstall pip dependencies"
	@echo "  make install-dev-deps   install dev/test deps (pytest)"
	@echo "  make wizard             run setup_wizard.py (re-prompt for .env, schemas, services)"
	@echo "  make doctor             run health checks (read-only)"
	@echo "  make agent              launch the agent REPL"
	@echo "  make refresh            run the daily refresh pipeline once"
	@echo "  make services-install   install launchd / systemd background services"
	@echo "  make services-uninstall remove background services"
	@echo "  make app                build a clickable macOS .app bundle"
	@echo "  make app-install        build and copy 'Agent Adda.app' to ~/Applications"
	@echo "  make package            build a redistributable tarball under dist/"
	@echo "  make package-dry        show what package would include (no tarball)"
	@echo "  make data-seed          dump current PG data → dist/agent-adda-data-*.tar.gz"
	@echo "  make data-seed-schema   dump schemas only (no rows) for clean DB skeleton"
	@echo "  make data-restore SEED=path/to/seed.tar.gz   restore a data seed"
	@echo "  make test               run pytest"
	@echo "  make uninstall          remove .venv and background services"
	@echo ""

install:
	@bash $(INSTALLER)/install.sh

install-system:
	@bash $(INSTALLER)/install.sh --skip-wizard

install-deps:
	@$(PIP) install --upgrade pip wheel setuptools
	@$(PIP) install -r $(ROOT)/requirements.txt

install-dev-deps:
	@$(PIP) install -r $(ROOT)/requirements-dev.txt

wizard:
	@$(PY) $(INSTALLER)/setup_wizard.py

doctor:
	@$(PY) $(INSTALLER)/doctor.py

agent:
	@cd $(ROOT) && $(PY) nse_agent.py

refresh:
	@cd $(ROOT) && $(PY) daily_refresh.py

services-install:
ifeq ($(UNAME_S),Darwin)
	@mkdir -p $(HOME)/Library/LaunchAgents
	@for f in $(INSTALLER)/launchd/*.plist.tmpl; do \
	    name=$$(basename $$f .tmpl); \
	    target=$(HOME)/Library/LaunchAgents/$$name; \
	    sed -e 's|__VENV__|$(VENV)|g' -e 's|__ROOT__|$(ROOT)|g' "$$f" > "$$target"; \
	    launchctl unload "$$target" 2>/dev/null || true; \
	    launchctl load "$$target" && echo "loaded $$name"; \
	done
else ifeq ($(UNAME_S),Linux)
	@mkdir -p $(HOME)/.config/systemd/user
	@for f in $(INSTALLER)/systemd/*.service $(INSTALLER)/systemd/*.timer; do \
	    [ -f "$$f" ] || continue; \
	    name=$$(basename $$f); \
	    target=$(HOME)/.config/systemd/user/$$name; \
	    sed -e 's|__VENV__|$(VENV)|g' -e 's|__ROOT__|$(ROOT)|g' "$$f" > "$$target"; \
	done
	@systemctl --user daemon-reload
	@systemctl --user enable --now agentadda-intraday-capture.service agentadda-daily-refresh.timer
else
	@echo "Service install not supported on $(UNAME_S)"
endif

services-uninstall:
ifeq ($(UNAME_S),Darwin)
	@for unit in com.agentadda.daily_refresh com.agentadda.intraday_capture; do \
	    target=$(HOME)/Library/LaunchAgents/$$unit.plist; \
	    [ -f "$$target" ] && launchctl unload "$$target" 2>/dev/null && rm "$$target" && echo "removed $$unit"; \
	done
else ifeq ($(UNAME_S),Linux)
	@systemctl --user disable --now agentadda-intraday-capture.service agentadda-daily-refresh.timer 2>/dev/null || true
	@rm -f $(HOME)/.config/systemd/user/agentadda-*.{service,timer}
	@systemctl --user daemon-reload
endif

app:
	@bash $(INSTALLER)/build_macos_app.sh

app-install:
	@bash $(INSTALLER)/build_macos_app.sh --user-install

package:
	@bash $(INSTALLER)/package_distribution.sh

package-dry:
	@bash $(INSTALLER)/package_distribution.sh --dry-run

data-seed:
	@bash $(INSTALLER)/package_data_seed.sh

data-seed-schema:
	@bash $(INSTALLER)/package_data_seed.sh --schemas-only

data-restore:
	@if [ -z "$(SEED)" ]; then echo "Usage: make data-restore SEED=path/to/agent-adda-data-*.tar.gz"; exit 1; fi
	@bash $(INSTALLER)/restore_data_seed.sh $(SEED)

test:
	@$(PY) -c "import pytest" 2>/dev/null || $(PIP) install -r $(ROOT)/requirements-dev.txt
	@cd $(ROOT) && $(PY) -m pytest tests/

clean:
	@find $(ROOT) -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find $(ROOT) -type f -name "*.pyc" -delete 2>/dev/null || true

uninstall: services-uninstall
	@rm -rf $(VENV)
	@echo "Removed $(VENV) and background services. .env preserved."
