import re2

from testtools.matchers import MatchesRegex

from tests.base import ZuulTestCase, simple_layout


class TestBitbucketFunctional(ZuulTestCase):
    config_file = 'zuul-bitbucket-driver.conf'

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_pull_request_opened(self):

        initial_comment = "This is the\nPR description."
        A = self.fake_bitbucket.openFakePullRequest(
            'project/repo', 'A test', 'master', 'foobar',
            description=initial_comment)
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['zuul']
        self.assertEqual(str(A.number), zuulvars['change'])
        self.assertEqual(str(A.head), zuulvars['patchset'])
        self.assertEqual('foobar', zuulvars['branch'])
        self.assertEqual(zuulvars["message"], initial_comment)
        self.assertEqual(2, len(self.history))
        self.assertEqual(2, len(A.comments))
        self.assertEqual(
            A.comments[0]['comment'], "Starting check jobs.")
        self.assertThat(
            A.comments[1]['comment'],
            MatchesRegex(r'.*\[project-test1 \]\(.*\).*', re2.DOTALL))
        self.assertThat(
            A.comments[1]['comment'],
            MatchesRegex(r'.*\[project-test2 \]\(.*\).*', re2.DOTALL))
        self.assertEqual(2, len(A.flags))
        self.assertEqual('success', A.flags[0]['status'])
        self.assertEqual('pending', A.flags[1]['status'])
