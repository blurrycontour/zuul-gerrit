# This Makefile is currently used only for development covenince for launching
# common testing commands during development. It is not used by any CI/CD jobs.
PYTHON ?= $(shell command -v python3 python|head -n1)

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
		print("  %-8s	%s" % (cmd, cmds[cmd]))
endef
export PRINT_HELP_PYSCRIPT

.PHONY: help
help:
	@$(PYTHON) -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

.PHONY: lint
lint:  ## Lint
	tox -e linters
	cd web && npm run lint

.PHONY: docs
docs:  ## Build docs
	tox -e docs

.PHONY: test
test:  ## Run python tests
	tox -e py3

.PHONY: docker
docker:  ## Run python tests inside a docker container
	tox -e py3-docker

.PHONY: nodepool
nodepool:  ## Run nodepool tests
	tox -e nodepool

.PHONY: clean
clean: ## Clean all git ignored files
	git clean -X -d -f

.PHONY: web
web: ## Runs the dashboard using openstack Zuul server as backend
	cd web && yarn install && yarn start:openstack
