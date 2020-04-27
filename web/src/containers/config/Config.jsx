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
      wrap: JSON.parse(localStorage.getItem('zuul_wrap', false)) === true
    }
    this.handleModalToggle = () => {
      this.setState(({ isModalOpen }) => ({
        isModalOpen: !isModalOpen
      }))
    }

    this.handleSave = () => {
        this.handleModalToggle()
        localStorage.setItem('zuul_wrap', this.state.wrap)
        document.documentElement.setAttribute('wrap', (this.state.wrap) ? 'enabled': null);
      }

    this.handleWrap = () => {
      this.setState(({ wrap }) => ({
        wrap: !wrap
      }))
    }
  }

  render() {
    const { isModalOpen, wrap } = this.state
    return (
      <React.Fragment>
        <Button
          variant={ButtonVariant.plain}
          key="cog"
          onClick={this.handleModalToggle}>
           <CogIcon />
        </Button>
        <Modal
          variant={ModalVariant.small}
          title="Preferences"
          isOpen={isModalOpen}
          onClose={this.handleModalToggle}
          actions={[
            <Button key="confirm" variant="primary" onClick={this.handleSave}>
              Confirm
            </Button>,
            <Button key="cancel" variant="link" onClick={this.handleModalToggle}>
              Cancel
            </Button>
          ]}
          >
            <div>
              <p key="info">User configurable settings are saved in browser local storage only.</p>
              <Switch
                key="wrap"
                id="wrap"
                label="Auto wrap log lines like terminals"
                isChecked={wrap}
                onChange={this.handleWrap}
              />
            </div>
        </Modal>
        </React.Fragment>
    )
  }
}

export default connect(state => ({
    wrap: state.wrap,
  }))(ConfigModal)
