// Copyright 2018 Red Hat, Inc
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

// The index is the main of the project. The App is wrapped with
// a Provider to share the redux store and a Router to manage the location.

import React from 'react'
import ReactDOM from 'react-dom'
import { BrowserRouter as Router } from 'react-router-dom'
import { Provider } from 'react-redux'
import 'patternfly/dist/css/patternfly.min.css'
import 'patternfly/dist/css/patternfly-additions.min.css'
import './index.css'

import { getHomepageUrl } from './api'
import registerServiceWorker from './registerServiceWorker'
import { fetchInfoIfNeeded } from './actions/info'
import { loginRequest, loginSuccess, login, loginFail } from './actions/auth'
import createZuulStore from './store'
import App from './App'

import Keycloak from 'keycloak-js'

const store = createZuulStore()

const unsubscribe = store.subscribe(() => console.log(store.getState()))

// Load info endpoint
store.dispatch(fetchInfoIfNeeded())

// Login by default

store.dispatch(loginRequest())
const keycloak = Keycloak("/keycloak.json")
keycloak.init({ onLoad: 'login-required' })
    .success(authenticated => {
        console.log('success!')
        console.log(keycloak.token)
        store.dispatch(loginSuccess(keycloak.token))
        store.dispatch(login(keycloak.token))
    })
       .error(err => {
           console.log('error!')
           store.dispatch(loginFail(err))
           alert(err)
           })


ReactDOM.render(
  <Provider store={store}>
    <Router basename={new URL(getHomepageUrl()).pathname}><App /></Router>
  </Provider>, document.getElementById('root'))
registerServiceWorker()
