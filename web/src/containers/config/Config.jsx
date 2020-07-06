// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

// import PropTypes from 'prop-types'
import React from 'react'
import { connect } from 'react-redux'
import {
  Button,
  ButtonVariant,
  Modal,
  ModalVariant,
  Switch
} from '@patternfly/react-core'
import { CogIcon } from '@patternfly/react-icons'

class ConfigModal extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
      isModalOpen: false,
      autoReload: JSON.parse(localStorage.getItem('zuul_auto_reload', false)) === true
    }
    this.handleModalToggle = () => {
      this.setState(({ isModalOpen }) => ({
        isModalOpen: !isModalOpen
      }))
    }

    this.handleAutoReload = () => {
      this.setState(({ autoReload }) => ({
        autoReload: !autoReload
      }))
      localStorage.setItem('zuul_auto_reload', this.state.autoReload)
      window.dispatchEvent(new Event('reconfig'))
    }
  }

  render() {
    const { isModalOpen, autoReload } = this.state
    return (
      <React.Fragment>
        <Button variant={ButtonVariant.plain} onClick={this.handleModalToggle}>
           <CogIcon />
        </Button>
        <Modal
          variant={ModalVariant.small}
          title="Preferences"
          isOpen={isModalOpen}
          onClose={this.handleModalToggle}
          actions={[
            <Button key="confirm" variant="primary" onClick={this.handleModalToggle}>
              Confirm
            </Button>,
            <Button key="cancel" variant="link" onClick={this.handleModalToggle}>
              Cancel
            </Button>
          ]}
          >
            <div>
              <p>User configurable settings are saved in browser local storage only.</p>
              <Switch
                id="autoreload"
                label="Auto reload status page"
                isChecked={autoReload}
                onChange={this.handleAutoReload}
              />
            </div>
        </Modal>
        </React.Fragment>
    )
  }
}

export default connect()(ConfigModal)
