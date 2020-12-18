// Copyright 2020 Red Hat, Inc
//
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

import React from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'

import {
  Accordion,
  AccordionItem,
  AccordionToggle,
  AccordionContent,
  Button,
  ButtonVariant,
  ClipboardCopy,
  ClipboardCopyVariant,
  Modal,
  ModalVariant
} from '@patternfly/react-core'
import {
  UserIcon,
  SignInAltIcon,
  SignOutAltIcon,
  HatWizardIcon
} from '@patternfly/react-icons'

import * as moment from 'moment'
import { UserManager } from 'oidc-react'

import { apiUrl } from '../../api'
import { userLoggingOut, userInStore } from '../../actions/user'
import stateStore from '../../stateStore'


class AuthContainer extends React.Component {
  static propTypes = {
    userManagerConfig: PropTypes.object,
    user: PropTypes.object,
    tenant: PropTypes.object,
    dispatch: PropTypes.func.isRequired,
    timezone: PropTypes.string.isRequired,
    info: PropTypes.object,
  }

  constructor(props) {
    super(props)
    const { tenant } = this.props
    this.state = {
      isModalOpen: false,
      showZuulClientConfig: false,
    }
    this.handleModalToggle = () => {
      this.setState(({ isModalOpen }) => ({
        isModalOpen: !isModalOpen
      }))
    }
    this.handleConfigToggle = () => {
      this.setState(({ showZuulClientConfig }) => ({
        showZuulClientConfig: !showZuulClientConfig
      }))
    }
    const stored_user = localStorage.getItem('zuul_user')
    if (stored_user !== null) {
      let user = JSON.parse(stored_user)
      const now = Date.now() / 1000
      if (user.expires_at > now) {
        this.props.dispatch(userInStore(user, tenant.name))
      }
    }
  }

  ZuulClientConfig(tenant, user) {
    let ZCconfig
    ZCconfig = '[' + tenant.name + ']\n'
    ZCconfig = ZCconfig + 'url=' + apiUrl.slice(0, -4) + '\n'
    ZCconfig = ZCconfig + 'tenant=' + tenant.name + '\n'
    ZCconfig = ZCconfig + 'auth_token=' + user.token + '\n'

    return ZCconfig
  }

  renderModal(user, userManager, tenant, timezone) {
    const { isModalOpen, showZuulClientConfig } = this.state
    let config = this.ZuulClientConfig(tenant, user)
    let valid_until = moment.unix(user.user.expires_at).tz(timezone).format('YYYY-MM-DD HH:mm:ss')
    return (
      <React.Fragment>
        <Modal
          variant={ModalVariant.small}
          title="User Info"
          isOpen={isModalOpen}
          onClose={this.handleModalToggle}
          actions={[
            <Button
              key="SignOut"
              variant="primary"
              onClick={() => {
                localStorage.setItem('zuul_auth_redirect', null)
                this.props.dispatch(userLoggingOut(userManager))
              }}
              title="Note that you will be logged out of Zuul, but not out of your identity provider.">
              Sign Out &nbsp;
              <SignOutAltIcon title='Sign Out' />
            </Button>
          ]}
        >
          <div>
            <p key="user">Name: <strong>{user.user.profile.name}</strong></p>
            <p key="preferred_username">Logged in as: <strong>{user.user.profile.preferred_username}</strong>&nbsp;
              {(user.isAdmin && user.scope.indexOf(tenant.name) !== -1) && (
                <HatWizardIcon title='This user can perform admin tasks' />
              )}</p>
            <Accordion asDefinitionList>
              <AccordionItem>
                <AccordionToggle
                  onClick={this.handleConfigToggle}
                  isExpanded={showZuulClientConfig}
                  title='Configuration parameters that can be used to perform tasks with the CLI'
                  id="ZCConfig">
                  Show Zuul Client Config
                </AccordionToggle>
                <AccordionContent
                  isHidden={!showZuulClientConfig}>
                  <ClipboardCopy isCode isReadOnly variant={ClipboardCopyVariant.expansion}>{config}</ClipboardCopy>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
            <p key="valid_until">Token expiry date: <strong>{valid_until}</strong></p>
            <p key="footer">
              Zuul stores and uses information such as your username
              and your email to provide some features. This data is stored
              <strong>in your browser only</strong> and is
              discarded once you log out.</p>
          </div>
        </Modal>
      </React.Fragment>
    )
  }

  renderButton(containerStyles) {

    const { user, userManagerConfig, tenant, timezone } = this.props
    const userManager = new UserManager(
      { ...userManagerConfig, stateStore: stateStore })
    if (!user.user) {
      return (
        <div style={containerStyles}>
          <Button
            key="SignIn"
            variant={ButtonVariant.plain}
            onClick={() => {
              localStorage.setItem('zuul_auth_redirect', window.location.href)
              userManager.signinRedirect()
            }}>
            Sign in &nbsp;
            <SignInAltIcon title='Sign In' />
          </Button>
        </div>
      )
    } else {
      return (user.isFetching ? <div style={containerStyles}>Loading...</div> :
        <div style={containerStyles}>
          {this.renderModal(user, userManager, tenant, timezone)}
          <Button
            variant={ButtonVariant.plain}
            key="userinfo"
            onClick={this.handleModalToggle}>
            <UserIcon title='User details' />
            &nbsp;{user.user.profile.preferred_username}&nbsp;
          </Button>
        </div>
      )
    }
  }

  render() {
    const { userManagerConfig, info } = this.props
    const textColor = '#d1d1d1'
    const containerStyles = {
      color: textColor,
      border: 'solid #2b2b2b',
      borderWidth: '0 0 0 1px',
      display: 'initial',
      padding: '6px'
    }
    if (info.isFetching) {
      return (<><div style={containerStyles}>Fetching auth info ...</div></>)
    }
    if (userManagerConfig) {
      return this.renderButton(containerStyles)
    } else {
      return (<div style={containerStyles} title="Authentication disabled">-</div>)
    }
  }
}

export default connect(state => ({
  userManagerConfig: state.auth.userManagerConfig,
  user: state.user,
  tenant: state.tenant,
  timezone: state.timezone,
  info: state.info,
}))(AuthContainer)
