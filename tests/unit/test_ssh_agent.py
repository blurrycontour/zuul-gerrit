import os
import tempfile
import subprocess

import fixtures
import testtools

from zuul.executor.server import SshAgent

class TestSshAgent(testtools.TestCase):
    def test_ssh_agent(self):
        # Need a private key to add
        self.useFixture(fixtures.NestedTempfile())
        keydir = tempfile.mkdtemp()
        key_path = os.path.join(keydir, 'id_rsa')
        env_copy = dict(os.environ)
        # DISPLAY and SSH_ASKPASS will cause interactive test runners to get a
        # surprise
        if 'DISPLAY' in env_copy:
            del env_copy['DISPLAY']
        if 'SSH_ASKPASS' in env_copy:
            del env_copy['SSH_ASKPASS']
        with open('/dev/null') as devnull:
            subprocess.check_call(['ssh-keygen', '-t', 'rsa', '-b', '1024', '-q',
                                   '-N', '', '-f', key_path],
                                  stdin=devnull, env=env_copy)
        agent = SshAgent()
        agent.start()
        env_copy.update(agent.env)

        pub_key_path = '{}.pub'.format(key_path)
        pub_key = None
        with open(pub_key_path) as pub_key_file:
            pub_key = pub_key_file.read().rsplit(' ', 1)[0]

        agent.add(key_path)
        keys = agent.list()
        self.assertEqual(1, len(keys))
        self.assertEqual(keys[0].rsplit(' ', 1)[0], pub_key)
        agent.remove(key_path)
        keys = agent.list()
        self.assertEqual([], keys)
        agent.stop()
        # Agent is now dead and thus this should fail
        self.assertRaises(subprocess.CalledProcessError, subprocess.check_call,
                          ['ssh-add', key_path], env=env_copy)
