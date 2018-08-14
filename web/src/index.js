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

import React from 'react';
import ReactDOM from 'react-dom';
import { HashRouter as Router } from 'react-router-dom';
import { createStore, applyMiddleware } from 'redux';
import thunk from 'redux-thunk';
import { Provider } from 'react-redux';
import 'patternfly/dist/css/patternfly.min.css';
import 'patternfly/dist/css/patternfly-additions.min.css';
import './index.css';

import rootReducer from './reducers';
import { fetchInfo } from './api';
import App from './App';
import registerServiceWorker from './registerServiceWorker';

const store = createStore(
  rootReducer, applyMiddleware(thunk));
store.dispatch(fetchInfo());

ReactDOM.render(
  <Provider store={store}>
    <Router><App /></Router>
  </Provider>, document.getElementById('root'));
registerServiceWorker();
