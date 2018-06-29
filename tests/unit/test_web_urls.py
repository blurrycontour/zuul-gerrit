#!/usr/bin/env python

# Copyright 2017 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json
import logging
import urllib
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import FirefoxOptions


from tests.base import ZuulTestCase, WebProxyFixture
from tests.base import ZuulWebFixture


class TestWebURLs(ZuulTestCase):
    tenant_config_file = 'config/single-tenant/main.yaml'

    def setUp(self):
        super(TestWebURLs, self).setUp()
        self.web = self.useFixture(
            ZuulWebFixture(self.gearman_server.port,
                           self.config))

    def _get(self, port, uri):
        url = "http://localhost:{}{}".format(port, uri)
        self.log.debug("GET {}".format(url))
        req = urllib.request.Request(url)
        try:
            f = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            raise Exception("Error on URL {}".format(url))
        return f.read()

    def _crawl(self, url):
        page = self._get(self.port, url)
        page = BeautifulSoup(page, 'html.parser')
        for (tag, attr) in [
                ('script', 'src'),
                ('link', 'href'),
                ('a', 'href'),
                ('img', 'src'),
        ]:
            for item in page.find_all(tag):
                suburl = item.get(attr)
                # Skip empty urls. Also skip the navbar relative link for now.
                # TODO(mordred) Remove when we have the top navbar link sorted.
                if suburl is None or suburl == "../":
                    continue
                link = urllib.parse.urljoin(url, suburl)
                self._get(self.port, link)


class TestWebSelenium(TestWebURLs):
    log = logging.getLogger("zuul.TestWebSelenium")

    def setUp(self):
        super().setUp()
        opts = FirefoxOptions()
        opts.add_argument("--headless")
        self.driver = webdriver.Firefox(firefox_options=opts)

    def tearDown(self):
        super().tearDown()
        self.driver.close()

    def check_js_errors(self):
        errors = []
        try:
            for log in self.driver.get_log('browser'):
                self.log.info("Log event recorded: %s", log)
                if log['level'] in ('SEVERE', ):
                    errors.append(log)
        except Exception:
            # This doesn't work yet with Firefox, see
            # https://github.com/mozilla/geckodriver/issues/284
            pass
        self.assertEquals([], errors)

    def _get_url(self, uri):
        return "http://localhost:{}{}".format(self.port, uri)

    def check_pipelines_list(self, pipelines=['check', 'gate', 'post']):
        # Wait for page load
        for i in range(3):
            pipelines_dom = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "zuul_pipelines"))
            )
            pipelines_headers = pipelines_dom.find_elements_by_class_name(
                "zuul-pipeline-header")
            if len(pipelines_headers):
                break
            time.sleep(3)
        self.assertEquals(len(pipelines_headers), len(pipelines))
        for pos in range(len(pipelines)):
            self.assertIn(pipelines[pos], pipelines_headers[pos].text)


class TestFunctionalWhiteLabel(TestWebSelenium):
    def setUp(self):
        super().setUp()
        rules = [
            ('^/(.*)$', 'http://localhost:{}/\\1'.format(self.web.port)),
        ]
        self.proxy = self.useFixture(WebProxyFixture(rules))
        self.port = self.proxy.port

    def test_functional_white_label_status_page(self):
        self.driver.get(self._get_url('/status.html'))
        self.assertIn("Zuul Status", self.driver.title)
        self.check_pipelines_list()
        self.check_js_errors()


class TestFunctionalDirect(TestWebSelenium):
    def setUp(self):
        super().setUp()
        self.port = self.web.port

    def test_functional_direct_status_page(self):
        self.driver.get(self._get_url('/t/tenant-one/status.html'))
        self.assertIn("Zuul Status", self.driver.title)
        self.check_pipelines_list()
        self.check_js_errors()


class TestDirect(TestWebURLs):
    # Test directly accessing the zuul-web server with no proxy
    def setUp(self):
        super(TestDirect, self).setUp()
        self.port = self.web.port

    def test_status_page(self):
        self._crawl('/t/tenant-one/status.html')


class TestWhiteLabel(TestWebURLs):
    # Test a zuul-web behind a whitelabel proxy (i.e., what
    # zuul.openstack.org does).
    def setUp(self):
        super(TestWhiteLabel, self).setUp()
        rules = [
            ('^/(.*)$', 'http://localhost:{}/\\1'.format(self.web.port)),
        ]
        self.proxy = self.useFixture(WebProxyFixture(rules))
        self.port = self.proxy.port

    def test_status_page(self):
        self._crawl('/status.html')


class TestWhiteLabelAPI(TestWebURLs):
    # Test a zuul-web behind a whitelabel proxy (i.e., what
    # zuul.openstack.org does).
    def setUp(self):
        super(TestWhiteLabelAPI, self).setUp()
        rules = [
            ('^/api/(.*)$',
             'http://localhost:{}/api/tenant/tenant-one/\\1'.format(
                 self.web.port)),
        ]
        self.proxy = self.useFixture(WebProxyFixture(rules))
        self.port = self.proxy.port

    def test_info(self):
        info = json.loads(self._get(self.port, '/api/info').decode('utf-8'))
        self.assertEqual('tenant-one', info['info']['tenant'])


class TestSuburl(TestWebURLs):
    # Test a zuul-web mounted on a suburl (i.e., what software factory
    # does).
    def setUp(self):
        super(TestSuburl, self).setUp()
        rules = [
            ('^/zuul3/(.*)$', 'http://localhost:{}/\\1'.format(
                self.web.port)),
        ]
        self.proxy = self.useFixture(WebProxyFixture(rules))
        self.port = self.proxy.port

    def test_status_page(self):
        self._crawl('/zuul3/t/tenant-one/status.html')
