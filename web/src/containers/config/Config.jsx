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
  Checkbox,
  Icon,
  Modal,
} from 'patternfly-react'

class Config extends React.Component {
   static propTypes = {
      dispatch: PropTypes.func
  }

  constructor(props) {
    super(props)
    this.state = {
      opened: false,
      autoReload: false
    }
    this.toggleBox = this.toggleBox.bind(this)
  }

  componentDidUpdate() {
    localStorage.setItem('zuul_auto_reload', this.state.autoReload)
    window.dispatchEvent(new Event('reconfig'))
  }

  toggleBox = () => {
    const { opened } = this.state
    this.setState({opened: !opened})
  }

  render() {
    const containerStyles= {
      border: 'solid #2b2b2b',
      borderWidth: '0 0 0 1px',
      cursor: 'pointer',
      display: 'initial',
      fontSize: '11px',
      padding: '6px'
    }
    const iconStyles = {
      padding: '5px'
    }
    const { opened, autoReload } = this.state
    return (
      <div style={containerStyles}>
      <Icon style={iconStyles} type="pf" name="settings" onClick={this.toggleBox}/>
      { opened && (
      <Modal key='modal' show={this.toggleBox} onHide={this.close}>
          <Modal.Header>
            <button
              className="close"
              onClick={this.handleDrawerToggle}
              aria-hidden="true"
              aria-label="Close"
            >
              <Icon type="pf" name="close" onClick={this.toggleBox}/>
            </button>
            <Modal.Title>Preferences</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            <Checkbox
              defaultChecked={autoReload}
              onChange={(e) => {this.setState({autoReload: e.target.checked})}}
              style={{marginTop: '0px'}}>
              auto reload
            </Checkbox>
          </Modal.Body>
      </Modal>
    )}
      </div>
    )
  }
}

export default connect()(Config)
