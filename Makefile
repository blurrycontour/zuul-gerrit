all: linters py27

.venv/venv .venv/linters .venv/py%:
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

py26: PYVERSION = python2.6
py26: export PYTHON = .venv/py26/bin/python
py26: .venv/py26
	if [ ! -d .testrepository ] ; then .venv/py26/bin/testr init ; fi
	.venv/py26/bin/testr run --parallel $(ARGS)

py27: PYVERSION = python2.7
py27: export PYTHON = .venv/py27/bin/python
py27: .venv/py27
	if [ ! -d .testrepository ] ; then .venv/py27/bin/testr init ; fi
	.venv/py27/bin/testr run --parallel $(ARGS)

py33: PYVERSION = python3.3
py33: export PYTHON = .venv/py33/bin/python
py33: .venv/py33
	if [ ! -d .testrepository ] ; then .venv/py33/bin/testr init ; fi
	.venv/py33/bin/testr run --parallel $(ARGS)

venv: PYVERSION = python
venv: export PYTHON = .venv/venv/bin/python
venv: .venv/venv
	. .venv/venv/bin/activate && $(ARGS)

clean:
	rm -rf .venv
