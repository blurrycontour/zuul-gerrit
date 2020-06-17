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
// TODO (felix): "Chicken egg problem": Usually, the PF4 CSS file should be
// included at the uppermost before the dedicated PF4 components (with their
// respective CSS) are imported.
// However, this has the drawback that PF3 CSS still might override respective
// PF4 CSS (e.g. the new font type and size).
// Importing PF4 after PF3 however, results in PF3 CSS rules being overwritten
// by some PF4 wildcards which breaks most of the layout due to padding and
// margin being set to 0 for most HTML tags.
import 'patternfly/dist/css/patternfly.min.css'
import 'patternfly/dist/css/patternfly-additions.min.css'
// NOTE (felix): The Patternfly 4 CSS file must be imported before the App
// component. Otherwise, the CSS rules are imported in the wrong order and some
// wildcard expressions could break the layout:
// https://forum.patternfly.org/t/wildcard-selector-more-specific-after-upgrade-to-patternfly-4-react-version-3-75-2/261
import "@patternfly/react-core/dist/styles/base.css";
// TODO (felix): Remove this import after the PF4 migration
import "./pf4-migration.css";
import './index.css'

import { getHomepageUrl } from './api'
import registerServiceWorker from './registerServiceWorker'
import { fetchInfoIfNeeded } from './actions/info'
import store from './store'
import App from './App'

// Load info endpoint
store.dispatch(fetchInfoIfNeeded())

ReactDOM.render(
  <Provider store={store}>
    <Router basename={new URL(getHomepageUrl()).pathname}><App /></Router>
  </Provider>, document.getElementById('root'))
registerServiceWorker()
