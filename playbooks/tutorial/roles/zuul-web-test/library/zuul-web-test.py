#!/usr/bin/env python3
# Copyright 2022 Guillaume Chauvel
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


from ansible.module_utils.basic import AnsibleModule

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def run():
    firefox_options = webdriver.FirefoxOptions()
    driver = webdriver.Remote(
        command_executor="http://127.0.0.1:4444", options=firefox_options
    )

    # To quickly test local updates to this role:
    # cd playbooks/tutorial
    # ansible -m include_role -a name=zuul-web-test localhost
    driver.get("http://127.0.0.1:9000/t/example-tenant/status")
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CLASS_NAME, "zuul-pipeline")))

    driver.find_element_by_xpath("//*[text()[contains(.,'check')]]")

    driver.find_element_by_xpath("//*[text()[contains(.,'gate')]]")

    driver.get("http://127.0.0.1:9000/t/example-tenant/builds")
    # Waiting for presence_of_element_located((By.CLASS_NAME, "zuul-table")))
    # and then looking for 'testjob' text is a bit flaky when running on
    # opendev, so wait for what we expect to find
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[text()[contains(.,'testjob')]]")))

    testjob = driver.find_elements_by_xpath(
        "//*[text()[contains(.,'testjob')]]")
    assert len(testjob) == 2, 'jobs "testjob" not found'

    noop = driver.find_elements_by_xpath(
        "//*[text()[contains(.,'noop')]]")
    assert len(noop) == 2, 'jobs "noop" not found'

    driver.quit()


def ansible_main():
    module = AnsibleModule(argument_spec=dict())

    try:
        run()
    except Exception as e:
        module.fail_json(changed=False, msg=str(e))
    module.exit_json(changed=True)


if __name__ == "__main__":
    ansible_main()
