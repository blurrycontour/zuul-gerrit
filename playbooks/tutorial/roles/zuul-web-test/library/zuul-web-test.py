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

    # In case of assert errors caused by a change that legitimatly modifies
    # zuul web pages layout, You can use Selenium extension in your browser
    # to get the new element data and update the following code.
    # Start a record and click on text area.
    #
    # To quickly test local updates to this role:
    # cd playbooks/tutorial
    # ansible -m include_role -a name=zuul-web-test localhost
    driver.get("http://127.0.0.1:9000/t/example-tenant/status")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "zuul-pipeline")))

    assert("check" in driver.find_element(
        By.CSS_SELECTOR, ".zuul-pipeline:nth-child(1) .pf-c-title"
    ).text), 'status: "check" not found'

    assert("gate" in driver.find_element(
        By.CSS_SELECTOR, ".zuul-pipeline:nth-child(2) .pf-c-title"
    ).text), 'status: "gate" not found'

    driver.get("http://127.0.0.1:9000/t/example-tenant/builds")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "zuul-table")))

    assert(driver.find_element(
        By.CSS_SELECTOR, "tr:nth-child(1) > .pf-m-break-word:nth-child(1)"
    ).text == "testjob"), 'builds: 2nd "testjob" not found'

    assert(driver.find_element(
        By.CSS_SELECTOR, "tr:nth-child(2) > .pf-m-break-word:nth-child(1)"
    ).text == "noop"), 'builds: 2nd "noop" not found'

    assert(driver.find_element(
        By.CSS_SELECTOR, "tr:nth-child(3) > .pf-m-break-word:nth-child(1)"
    ).text == "noop"), 'builds: 1st "noop" not found'

    assert(driver.find_element(
        By.CSS_SELECTOR, "tr:nth-child(4) > .pf-m-break-word:nth-child(1)"
    ).text == "testjob"), 'builds: 1st "testjob" not found'

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
