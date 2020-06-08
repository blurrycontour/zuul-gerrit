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

    renderButton() {
        const { user, userManager } = this.props
        if (!user.user) {
            return (
                <button onClick={() => {userManager.signinRedirect()}}>Sign in</button>
            )
        } else {
            return (user.isFetching ? <div>Loading user ...</div> :
                <div>
                  Hello { user.user.profile.name }&nbsp;
                  <button onClick={() => { this.props.dispatch(userLoggingOut(userManager)) }}>Sign out</button>
                </div>
            )
        }
    }

    render () {
        const { userManager } = this.props
        if (userManager) {
            loadUser(store, userManager)
            return (
                <OidcProvider store={store} userManager={userManager}>
                  { this.renderButton() }
                </OidcProvider>
            )
        } else {
            return (<p>Loading ...</p>)
        }
    }
}

export default connect(state => ({
    userManager: state.auth.userManager,
    user: state.user,
}))(AuthContainer)
