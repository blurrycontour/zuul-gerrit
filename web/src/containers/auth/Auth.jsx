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

// The App is the parent component of every pages. Each page content is
// rendered by the Route object according to the current location.

import store from '../../store'
import { OidcProvider } from 'redux-oidc'
import { loadUser } from 'redux-oidc'
import { Icon } from 'patternfly-react'

import PropTypes from 'prop-types'
import React from 'react'
import { connect } from 'react-redux'
import { userLoggingOut } from '../../actions/user'

class AuthContainer extends React.Component {
    static propTypes = {
        userManager: PropTypes.object,
        user: PropTypes.object,
        dispatch: PropTypes.func.isRequired,
    }

    renderButton (containerStyles) {
        const iconStyles = {
          padding: '5px'
        }
        const { user, userManager } = this.props
        if (!user.user) {
            return (
              <div style={containerStyles}>
                <button className='btn btn-default' onClick={() => {userManager.signinRedirect()}}><Icon style={iconStyles} type="fa" name="sign-in" title='Sign Out' />Sign in</button>
              </div>
            )
        } else {
            return (user.isFetching ? <div style={containerStyles}>Loading...</div> :
                <div style={containerStyles}>
                  <span style={iconStyles} className='pficon pficon-user' title='user logged in' />
                  &nbsp;{ user.user.profile.name }&nbsp;
                  <button className='btn btn-default' onClick={() => { this.props.dispatch(userLoggingOut(userManager)) }}><Icon style={iconStyles} type="fa" name="sign-out" title='Sign Out' />Sign out</button>
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
          fontSize: '11px',
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
            return (<div style={containerStyles}>Anonymous Access</div>)
        }
    }
}

export default connect(state => ({
    userManager: state.auth.userManager,
    user: state.user,
}))(AuthContainer)
