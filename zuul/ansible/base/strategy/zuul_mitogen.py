import ansible_mitogen.plugins.strategy.mitogen_linear
import logging

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class StrategyModule(
    ansible_mitogen.plugins.strategy.mitogen_linear.StrategyModule):
    pass


# patch mitogen logging
old_setup = ansible_mitogen.logging.setup


def logging_setup():
    old_setup()

    l_mitogen = logging.getLogger('mitogen')
    # If we run ansible in verbose mode mitogen sets the mitogen backend
    # logging to debug which is way to excessive and causes problems. Reset
    # that to info in this case.
    if display.verbosity > 2:
        l_mitogen.setLevel(logging.INFO)


ansible_mitogen.logging.setup = logging_setup
