# This Makefile is currently used only for development covenince for launching
# common testing commands during development. It is not used by any CI/CD jobs.
PYTHON ?= $(shell command -v python3 python|head -n1)
PKG_MANAGER ?= $(shell command -v dnf yum|head -n1)
CONTAINER_RUNTIME := $(shell command -v podman 2> /dev/null || echo docker)

.PHONY: all
all: help

.PHONY: default
default: help

define PRINT_HELP_PYSCRIPT
import re, sys

print("Usage: make <target>\n")
cmds = {}
for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
	  target, help = match.groups()
	  cmds.update({target: help})
for cmd in sorted(cmds):
		print("  %s		%s" % (cmd, cmds[cmd]))
endef
export PRINT_HELP_PYSCRIPT

.PHONY: help
help:
	@$(PYTHON) -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

.PHONY: lint
lint:  ## Lint
	tox -e linters
	cd web && npm run lint --verbose

.PHONY: docs
docs:  ## Build docs
	tox -e docs

.PHONY: clean
clean: ## Clean artifacts
	rm -rf \
		.eggs \
		docs/build

.PHONY: dash
dash: ## Runs the dashboard using openstack Zuul server as backend
	cd web && yarn start:openstack

