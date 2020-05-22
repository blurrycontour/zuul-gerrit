import unittest

from hello import hello


class TestHello(unittest.TestCase):
    def test_hello(self):
        self.assertEqual(hello.Hello().run(), 'Hello Zuul')
