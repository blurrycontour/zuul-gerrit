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
// NOTE (felix): The Patternfly 4 CSS file must be imported before the App
// component. Otherwise, the CSS rules are imported in the wrong order and some
// wildcard expressions could break the layout:
// https://forum.patternfly.org/t/wildcard-selector-more-specific-after-upgrade-to-patternfly-4-react-version-3-75-2/261
// Usually it should be imported at the uppermost positon, but as we don't want
// PF3 to overrule PF4, we import PF4 styles after PF3.
import '@patternfly/react-core/dist/styles/base.css'
import '@patternfly/react-styles/css/utilities/Sizing/sizing.css'
import '@patternfly/react-styles/css/utilities/Spacing/spacing.css'
// To avoid that PF4 breaks existing PF3 components by some wildcard CSS rules,
// we include our own migration CSS file that restores relevant parts of those
// rules.
// TODO (felix): Remove this import after the PF4 migration
import './pf4-migration.css'

import { getHomepageUrl } from './api'
import registerServiceWorker from './registerServiceWorker'
import { fetchInfoIfNeeded } from './actions/info'
import configureStore from './store'
import App from './App'

// Importing our custom css file after the App allows us to also overwrite the
// style attributes of PF4 component (as their CSS is loaded when the component
// is imported within the App).
import './index.css'

const store = configureStore()

// Load info endpoint
store.dispatch(fetchInfoIfNeeded())

ReactDOM.render(
  <Provider store={store}>
    <Router basename={new URL(getHomepageUrl()).pathname}><App /></Router>
  </Provider>, document.getElementById('root'))
registerServiceWorker()
