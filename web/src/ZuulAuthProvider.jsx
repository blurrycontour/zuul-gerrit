// Copyright 2020 Red Hat, Inc
// Copyright 2021 Acme Gating, LLC
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
import PropTypes from 'prop-types'
import { connect } from 'react-redux'

import { AuthProvider } from 'oidc-react';
import { userLoggedIn, userLoggedOut } from './actions/user'


class ZuulAuthProvider extends React.Component {
  /*
    This wraps the oidc-react AuthProvider and supplies the necessary
    information as props.

    The oidc-react AuthProvider is not really meant to be reconstructed
    frequently. Calling render multiple times (even if nothing actually
    changes) during a login can cause multiple AuthProviders to be created
    which can interfere with the login process.

    We connect this class to state.auth.auth_params, so make sure that isn't
    updated unless the OIDC parameters are actually changed.

    If they are changed, then we will create a new AuthProvider with the
    new parameters.  Save those parameters in local storage so that when
    we return from the IDP redirect, an AuthProvider with the same
    configuration is created.
   */
  static propTypes = {
    auth_params: PropTypes.object,
    dispatch: PropTypes.func,
  }

  render () {
    const { auth_params } = this.props

    console.debug('ZuulAuthProvider rendering with params', auth_params)

    const oidcConfig = {
      onSignIn: async (user) => {
        this.props.dispatch(userLoggedIn(user))
        window.location.hash = '';
      },
      onSignOut: async () => {
        this.props.dispatch(userLoggedOut())
      },
      responseType: 'token id_token',
      autoSignIn: false,
      ...auth_params,
    };
    return (
      <React.Fragment>
        <AuthProvider {...oidcConfig} key={JSON.stringify(auth_params)}>
          {this.props.children}
        </AuthProvider>
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  auth_params: state.auth.auth_params,
}))(ZuulAuthProvider)
