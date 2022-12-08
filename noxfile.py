import os

import nox

def set_env(session, var, default):
    session.env[var] = os.environ.get(var, default)

def set_standard_env_vars(session):
    set_env(session, 'OS_LOG_CAPTURE', '1')
    set_env(session, 'OS_STDERR_CAPTURE', '1')
    set_env(session, 'OS_STDOUT_CAPTURE', '1')
    set_env(session, 'OS_TEST_TIMEOUT', '360')
    set_env(session, 'SQLALCHEMY_WARN_20', '1')
    session.env['PYTHONWARNINGS'] = 'always::DeprecationWarning:zuul.driver.sql.sqlconnection,always::DeprecationWarning:tests.base,always::DeprecationWarning:tests.unit.test_database,always::DeprecationWarning:zuul.driver.sql.alembic.env,always::DeprecationWarning:zuul.driver.sql.alembic.script'

@nox.session(python='python3')
def bindep(session):
    set_standard_env_vars(session)
    set_env(session, 'SQLALCHEMY_WARN_20', '1')
    session.install('bindep')
    session.install('.')
    session.run('bindep', 'test')

@nox.session(python='python3')
def cover(session):
    set_standard_env_vars(session)
    session.env['PYTHON'] = 'coverage run --source zuul --parallel-mode'
    session.install('-r/home/corvus/git/zuul/zuul/requirements.txt', '-r/home/corvus/git/zuul/zuul/test-requirements.txt')
    session.install('-e', '.')
    session.run('stestr', 'run')
    session.run('coverage', 'combine')
    session.run('coverage', 'html', '-d', 'cover')
    session.run('coverage', 'xml', '-o', 'cover/coverage.xml')

@nox.session(python='python3')
def docs(session):
    set_standard_env_vars(session)
    session.install('-r/home/corvus/git/zuul/zuul/doc/requirements.txt', '-r/home/corvus/git/zuul/zuul/test-requirements.txt')
    session.install('-e', '.')
    session.run('sphinx-build', '-E', '-W', '-d', 'doc/build/doctrees', '-b', 'html', 'doc/source/', 'doc/build/html')

@nox.session(python='python3')
def linters(session):
    set_standard_env_vars(session)
    session.install('flake8', 'openapi-spec-validator')
    session.install('.')
    session.run('flake8')
    session.run('openapi-spec-validator', 'web/public/openapi.yaml')

@nox.session(python='python3')
def py3(session):
    set_standard_env_vars(session)
    session.install('-r/home/corvus/git/zuul/zuul/requirements.txt', '-r/home/corvus/git/zuul/zuul/test-requirements.txt')
    session.install('-e', '.')
    # TODO rest of tools/pip.sh
    session.run_always('zuul-manage-ansible', '-v')
    session.run('bash', '-c', 'stestr run --slowest --concurrency=`python -c "import multiprocessing; print(max(int(multiprocessing.cpu_count()-1),1))"` ')

@nox.session(python='python3')
def remote(session):
    set_standard_env_vars(session)
    session.install('-r/home/corvus/git/zuul/zuul/requirements.txt', '-r/home/corvus/git/zuul/zuul/test-requirements.txt')
    session.install('-e', '.')
    session.run('stestr', 'run', '--test-path', './tests/remote')

@nox.session(python='python3')
def venv(session):
    set_standard_env_vars(session)
    session.install('-r/home/corvus/git/zuul/zuul/requirements.txt', '-r/home/corvus/git/zuul/zuul/test-requirements.txt')
    session.install('-e', '.')
    session.run()

@nox.session(python='python3')
def zuul_client(session):
    set_standard_env_vars(session)
    session.install('zuul-client', '-r/home/corvus/git/zuul/zuul/test-requirements.txt', '-r/home/corvus/git/zuul/zuul/requirements.txt')
    session.install('-e', '.')
    session.run('stestr', 'run', '--concurrency=1', '--test-path', './tests/zuul_client')
