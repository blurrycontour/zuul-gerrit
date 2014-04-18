.PHONY: all linters py26 py27 py33 venv clean

all: linters py27

.venv/%:
	# Note this line being the first dependency of anything python
	# related Make fail fast in the case of that version of python
	# not existing.
	virtualenv -p $(PYVERSION) $@
	$@/bin/pip install --upgrade -r requirements.txt -r test-requirements.txt
	$@/bin/pip install -e .

linters: PYVERSION = python
linters: export PYTHON = .venv/linters/bin/python
linters: .venv/linters
	.venv/linters/bin/flake8 $(ARGS)

venv: PYVERSION = python
venv: export PYTHON = .venv/venv/bin/python
venv: .venv/venv
	. .venv/venv/bin/activate && $(ARGS)

clean:
	rm -rf .venv

# Restrict second expansion to py% targets.
.SECONDEXPANSION:
py%: export PYTHON = .venv/$@/bin/python
py26: PYVERSION = python2.6
py27: PYVERSION = python2.7
py33: PYVERSION = python3.3
py26 py27 py33: .venv/$$@
	if [ ! -d .testrepository ] ; then .venv/$@/bin/testr init ; fi
	.venv/$@/bin/testr run --parallel $(ARGS)
