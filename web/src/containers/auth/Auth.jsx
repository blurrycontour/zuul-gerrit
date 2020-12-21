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

import configureStore from '../../store'
import { OidcProvider } from 'redux-oidc'
import { loadUser } from 'redux-oidc'
import { Accordion,
         AccordionItem,
         AccordionToggle,
         AccordionContent,
         Button,
         ButtonVariant,
         Modal,
         ModalVariant } from '@patternfly/react-core'
import { UserIcon,
         SignInAltIcon,
         SignOutAltIcon,
         HatWizardIcon } from '@patternfly/react-icons'

import PropTypes from 'prop-types'
import React from 'react'
import { connect } from 'react-redux'
import { userLoggingOut } from '../../actions/user'


const store = configureStore()


class AuthContainer extends React.Component {
    static propTypes = {
        userManager: PropTypes.object,
        user: PropTypes.object,
        tenant: PropTypes.object,
        dispatch: PropTypes.func.isRequired,
    }

    constructor(props) {
        super(props)
        this.state = {
            isModalOpen: false,
            showToken: false,
        }
        this.handleModalToggle = () => {
            this.setState(({ isModalOpen }) => ({
                isModalOpen: !isModalOpen
            }))
        }
        this.handleTokenToggle = () => {
            this.setState(({ showToken }) => ({
                showToken: !showToken
            }))
        }
    }

    renderModal(user, userManager, tenant) {
        const { isModalOpen , showToken } = this.state
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
                        onClick={() => { this.props.dispatch(userLoggingOut(userManager)) }}>
                      Sign Out &nbsp;
                      <SignOutAltIcon title='Sign Out' />
                    </Button>
                ]}
            >
              <div>
                <p key="user">Name: <strong>{user.user.profile.name}</strong></p>
                <p key="preferred_username">Logged in as: <strong>{ user.user.profile.preferred_username }</strong>&nbsp;
                {(user.isAdmin && user.scope.indexOf(tenant.name) !== -1 ) && (
                    <HatWizardIcon title='This user can perform admin tasks' />
                )}</p>
            <p key="token">
                <Accordion asDefinitionList>
                    <AccordionItem>
                        <AccordionToggle
                          onClick={this.handleTokenToggle}
                          isExpanded={showToken}
                          id="token">
                            User Token
                        </AccordionToggle>
                        <AccordionContent
                          isHidden={!showToken}>
                            { user.token }
                        </AccordionContent>
                    </AccordionItem>
                </Accordion>
            </p>
              </div>
            </Modal>
          </React.Fragment>
        )
    }

    renderButton (containerStyles) {

        const { user, userManager, tenant } = this.props
        if (!user.user) {
            return (
              <div style={containerStyles}>
                <Button
                  key="SignIn"
                  variant={ButtonVariant.plain}
                  onClick={() => {userManager.signinRedirect()}}>
                    Sign in &nbsp;
                    <SignInAltIcon title='Sign In' />
                </Button>
              </div>
            )
        } else {
            return (user.isFetching ? <div style={containerStyles}>Loading...</div> :
                <div style={containerStyles}>
                  { this.renderModal(user, userManager, tenant) }
                  <Button
                    variant={ButtonVariant.plain}
                    key="userinfo"
                    onClick={this.handleModalToggle}>
                      <UserIcon title='User details'  />
                  &nbsp;{ user.user.profile.preferred_username }&nbsp;
                  </Button>
                </div>
            )
        }
    }

    render () {
        const { userManager } = this.props
        const textColor = '#d1d1d1'
        const containerStyles= {
          color: textColor,
          border: 'solid #2b2b2b',
          borderWidth: '0 0 0 1px',
          display: 'initial',
          padding: '6px'
        }
        if (userManager) {
            loadUser(store, userManager)
            return (
                <OidcProvider store={store} userManager={userManager}>
                  { this.renderButton(containerStyles) }
                </OidcProvider>
            )
        } else {
            return (<div style={containerStyles} title="Authentication disabled">-</div>)
        }
    }
}

export default connect(state => ({
    userManager: state.auth.userManager,
    user: state.user,
    tenant: state.tenant,
}))(AuthContainer)
