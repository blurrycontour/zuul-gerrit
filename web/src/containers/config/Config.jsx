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

import PropTypes from 'prop-types'
import React from 'react'
import { connect } from 'react-redux'
import {
  Button,
  ButtonVariant,
  Form,
  FormGroup,
  Modal,
  ModalVariant,
  Switch
} from '@patternfly/react-core'
import Timezone from './Timezone'
import { CogIcon } from '@patternfly/react-icons'
import { setPreference } from '../../actions/preferences'


class ConfigModal extends React.Component {

  static propTypes = {
    location: PropTypes.object,
    tenant: PropTypes.object,
    preferences: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  constructor(props) {
    super(props)
    this.state = {
      isModalOpen: false,
      autoReload: false,
      timezone: null
     }

    this.handleModalToggle = () => {
      this.setState(({ isModalOpen }) => ({
        isModalOpen: !isModalOpen
      }))
      this.resetState()
    }

    this.handleSave = () => {
      this.handleModalToggle()
      this.props.dispatch(setPreference('autoReload', this.state.autoReload))
      this.props.dispatch(setPreference('timezone', this.state.timezone))
    }

    this.handleAutoReload = () => {
      this.setState(({ autoReload }) => ({
        autoReload: !autoReload
      }))
    }

    this.handleTimezone = (timezone) => {
      this.setState({timezone})
    }
  }

  resetState() {
    this.setState({
      autoReload: this.props.preferences.autoReload,
      timezone: this.props.preferences.timezone
    })
  }

  render() {
    const { isModalOpen, autoReload, timezone } = this.state
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
              <Form>
                <FormGroup>
                  <Switch
                    key="autoreload"
                    id="autoreload"
                    label="Auto reload status page"
                    isChecked={autoReload}
                    onChange={this.handleAutoReload}
                  />
                </FormGroup>
                <FormGroup label="Select result display timezone">
                  <Timezone
                    selected={timezone}
                    onSelect={this.handleTimezone}/>
                </FormGroup>
              </Form>
            </div>
        </Modal>
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  preferences: state.preferences,
}))(ConfigModal)
