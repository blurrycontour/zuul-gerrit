// Copyright 2019 Red Hat, Inc
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


import * as React from 'react'
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import { Button } from 'patternfly-react'

import * as actions from '../actions/user'

class UserLogin extends React.Component {

    logOut () {
        console.log('logging out')
        this.props.dispatch(actions.logout())
    }

    logIn () {
        console.log('logging in')
        this.props.dispatch(actions.loginIfNeeded(false))
    }

    renderLogin () {
        return (
            <Button onClick={e => { this.logIn() }}>Log in</Button>
        )
    }

    renderUser () {
        this.kc.loadUserInfo().then(userInfo => {
            return (
                <div>
                    Hello <strong>{ userInfo.username } </strong>
                    <Button onClick={e => { this.logOut() }}>Log out</Button>
                </div>
            )
        })
    }

    render () {
        if (!this.kc) {
            return this.renderLogin()
        }
        else {
            return this.renderUser()
        }
    }
}

export default connect(state => ({kc: state.user.kc}))(UserLogin)
