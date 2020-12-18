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


import * as React from 'react'
import { connect } from 'react-redux'
import { matchPath } from 'react-router'
import { CallbackComponent } from 'redux-oidc'
import { userLoggedIn } from '../actions/user'
import { Fetching } from '../containers/Fetching'

import PropTypes from 'prop-types'


class AuthCallbackPage extends React.Component {
    static propTypes = {
      history: PropTypes.object,
      dispatch: PropTypes.func.isRequired,
      userManager: PropTypes.object,
      location: PropTypes.object
    }

  successCallback = (user) => {
      let redirect = '/'
      const match = matchPath(
        this.props.location.pathname, {path: '/t/:tenant'})
      if (match) {
        let tenantName = match.params.tenant
        redirect += 't/' + tenantName + '/status'
        this.props.dispatch(userLoggedIn(user, tenantName))
      }
      this.props.history.push(redirect)
  }

  errorCallback = (error) => {
      console.log(error)
      this.props.history.push('/')
  }


  render() {
    const { userManager } = this.props
    return (
      <React.Fragment>
      { userManager ? (
      <CallbackComponent
        userManager={userManager}
        successCallback={this.successCallback}
        errorCallback={this.errorCallback}
        >
        <div>Login successful. You will be redirected shortly...</div>
      </CallbackComponent>) : <Fetching />
      }
      </React.Fragment>
    )
  }
}
export default connect(state =>({
  userManager: state.auth.userManager
}))(AuthCallbackPage)
