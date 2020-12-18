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


import React, { useEffect } from 'react'
import { connect, useDispatch } from 'react-redux'
import PropTypes from 'prop-types'
import { matchPath } from 'react-router'

import { UserManager } from 'oidc-react'

import { userLoggedIn } from '../actions/user'
import { Fetching } from '../containers/Fetching'

import stateStore from '../stateStore'

function AuthCallbackPage(userManagerConfig) {

  const dispatch = useDispatch()

  /* TODO(mhu) useEffect is called several times, which triggers the following
     error in signinRedirectCallback after the first successful call:
     
     Error: No matching state found in storage
     
     This is because the state parameter passed to the callback URL is consumed
     the first time and disappears from the oidc-client state store.
     
     Since this is unlikely to open the GUI to replay attacks (as the state is validated
     once) we can safely discard the error branch in signinRedirectCallback's return
     Promise. It would be good however to find a way to ensure useEffect, or at least
     the call to signinRedirectCallback within it, is run only once.*/
  useEffect(() => {
    if (userManagerConfig) {
      const currentUrl = window.location.href
      const manager = new UserManager(
        { ...userManagerConfig, stateStore: stateStore })
      const match = matchPath(
        window.location.pathname, { path: '/t/:tenant' })
      if (match) {
        let tenantName = match.params.tenant
        manager.signinRedirectCallback(currentUrl).then((user) => {
          dispatch(userLoggedIn(user, tenantName))
          let redirect = localStorage.getItem('zuul_auth_redirect')
          if (redirect) {
            // TODO(mhu) This reloads the whole page. Could we have a "soft" redirection instead
            // like when changing pages from the menu bar?
            window.location.replace(redirect)
          }
        }).catch(
          // (err) => {
          //   console.log(err)
          () => {
          })
      }
    }
  },
    // providing a dependency array doesn't seem to solve the problem with multiple calls 
    // to useEffect() mentioned above, left as a comment for documentation
    //    [userManagerConfig, dispatch]
  )
  if (userManagerConfig) {
    return (<div>Login successful. You will be redirected shortly...</div>)
  } else {
    return <Fetching />
  }

}

AuthCallbackPage.propTypes = {
  userManagerConfig: PropTypes.object,
}

export default connect((state) => ({
  userManagerConfig: state.auth.userManagerConfig
}))(AuthCallbackPage)