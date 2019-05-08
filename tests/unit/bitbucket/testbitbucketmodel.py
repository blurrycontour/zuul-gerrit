
from zuul.driver.bitbucket.bitbucketmodel import PullRequest
from tests.base import BaseTestCase


class TestBitbucketModel(BaseTestCase):
    def test_isUpdateOf(self):
        pr_a = PullRequest('aaa')
        pr_a.id = 101
        pr_a.patchset = ['foo', 'bar']
        pr_a.updatedDate = 1060

        pr_b = PullRequest('aaa')
        pr_b.id = 101
        pr_b.patchset = ['foo', 'xyz']
        pr_b.updatedDate = 2120

        pr_c = PullRequest('ccc')
        pr_c.id = 101
        pr_c.patchset = ['foo', 'bar']
        pr_c.updatedDate = 1060

        self.assertFalse(pr_a.isUpdateOf(pr_b))
        self.assertTrue(pr_b.isUpdateOf(pr_a))
        self.assertFalse(pr_c.isUpdateOf(pr_a))
