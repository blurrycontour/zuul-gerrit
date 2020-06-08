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

import PropTypes from 'prop-types'
import React from 'react'
import { connect } from 'react-redux'
import store from '../../store'
import { OidcProvider } from 'redux-oidc'
import { loadUser } from 'redux-oidc'


class Login extends React.Component {
   static propTypes = {
       userManager: PropTypes.object,
   }

   render() {
       console.log('this props', this.props)
       console.log('getState', store.getState())
       const { userManager } = this.props
       console.log('userManager:', userManager)
       if (userManager) {
           loadUser(store, userManager)
           return (
               <OidcProvider store={store} userManager={userManager}>
                   <div>
                      <button onClick={() => {userManager.signinRedirect()}}>Sign in</button>
                   </div>
               </OidcProvider>
           )
       } else {
           return (<div></div>)
       }
   }
}

export default connect(state =>({
    userManager: state.auth.userManager,
}))(Login)
