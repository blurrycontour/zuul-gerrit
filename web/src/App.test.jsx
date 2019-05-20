/* global Promise, expect, jest, it, location */
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

import React from 'react'
import ReactTestUtils from 'react-dom/test-utils'
import ReactDOM from 'react-dom'
import { act } from 'react-dom/test-utils'
import { Link, BrowserRouter as Router } from 'react-router-dom'
import { Provider } from 'react-redux'

import { fetchInfoIfNeeded } from './actions/info'
import createZuulStore from './store'
import App from './App'
import TenantsPage from './pages/Tenants'
import StatusPage from './pages/Status'
import * as api from './api'

api.fetchInfo = jest.fn()
api.fetchTenants = jest.fn()
api.fetchStatus = jest.fn()
api.fetchConfigErrors = jest.fn()
api.fetchConfigErrors.mockImplementation(() => Promise.resolve({data: []}))


it('renders without crashing', () => {
  const div = document.createElement('div')
  const store = createZuulStore()
  ReactDOM.render(<Provider store={store}><Router><App /></Router></Provider>,
    div)
  ReactDOM.unmountComponentAtNode(div)
})

it('renders multi tenant', () => {
  api.fetchInfo.mockImplementation(
    () => Promise.resolve({data: {
      info: {capabilities: {}}
    }})
  )
  api.fetchTenants.mockImplementation(
    () => Promise.resolve({data: [{name: 'openstack'}]})
  )
  const store = createZuulStore()
  const application = ReactTestUtils.renderIntoDocument(
    <Provider store={store}><Router><App /></Router></Provider>
  )
  store.dispatch(fetchInfoIfNeeded()).then(() => {
    // Link should be tenant scoped
    const topMenuLinks = ReactTestUtils.scryRenderedComponentsWithType(
      application, Link)
    expect(topMenuLinks[0].props.to).toEqual('/t/openstack/status')
    expect(topMenuLinks[1].props.to).toEqual('/t/openstack/projects')
    // Location should be /tenants
    expect(location.pathname).toEqual('/tenants')
    // Info should tell multi tenants
    expect(store.getState().info.tenant).toEqual(undefined)
    // Tenants list has been rendered
    expect(ReactTestUtils.findRenderedComponentWithType(
      application, TenantsPage)).not.toEqual(null)
    // Fetch tenants has been called
    expect(api.fetchTenants).toBeCalled()
  })
})

it('renders single tenant', () => {
  api.fetchInfo.mockImplementation(
    () => Promise.resolve({data: {
      info: {capabilities: {}, tenant: 'openstack'}
    }})
  )
  api.fetchStatus.mockImplementation(
    () => Promise.resolve({data: {pipelines: []}})
  )
  const store = createZuulStore()
  const application = ReactTestUtils.renderIntoDocument(
    <Provider store={store}><Router><App /></Router></Provider>
  )

  store.dispatch(fetchInfoIfNeeded()).then(() => {
    // Link should be white-label scoped
    const topMenuLinks = ReactTestUtils.scryRenderedComponentsWithType(
      application, Link)
    expect(topMenuLinks[0].props.to).toEqual('/status')
    expect(topMenuLinks[1].props.to).toEqual('/projects')
    // Location should be /status
    expect(location.pathname).toEqual('/status')
    // Info should tell white label tenant openstack
    expect(store.getState().info.tenant).toEqual('openstack')
    // Status page has been rendered
    expect(ReactTestUtils.findRenderedComponentWithType(
      application, StatusPage)).not.toEqual(null)
    // Fetch status has been called
    expect(api.fetchStatus).toBeCalled()
  })
})

it('renders config errors', () => {
  api.fetchInfo.mockImplementation(
    () => Promise.resolve({data: {
      info: {capabilities: {}, tenant: 'opendev'}
    }})
  )
  api.fetchStatus.mockImplementation(
    () => Promise.resolve({data: {pipelines: []}})
  )
  api.fetchConfigErrors.mockImplementation(
    () => Promise.resolve({data: [{
      error: 'Zuul encountered a syntax error',
      source_context: {
        project: 'config',
        branch: 'master',
        path: 'zuul.yaml'
      }}, {
      error: 'Zuul encountered another syntax error',
      source_context: {
        project: 'config',
        branch: 'master',
        path: 'zuul.yaml'
      }}]})
  )
  const store = createZuulStore()
  // Use ReactDOM.render to be able to simulate clicks, see:
  // https://reactjs.org/docs/test-utils.html#act
  const container = document.createElement('div')
  document.body.appendChild(container)
  act(() => {
    ReactDOM.render(
      <Provider store={store}><Router><App /></Router></Provider>, container)
  })

  store.dispatch(fetchInfoIfNeeded()).then(() => {
    try {
      const bell = container.querySelector('.fa-bell')
      expect(bell).not.toEqual(null)
      act(() => {
        bell.dispatchEvent(new MouseEvent('click', {bubbles: true}))
      })
      const drawer = container.querySelector('.drawer-pf-notifications')
      expect(drawer).not.toEqual(null)
      const items = container.querySelectorAll(
        '.drawer-pf-notification-message')
      expect(items[0].textContent).toEqual(
        'Zuul encountered a syntax error')
      expect(items[1].textContent).toEqual(
        'Zuul encountered another syntax error')
    } catch (error) {
      // Ensure error result in test failing
      expect(error).toEqual(undefined)
    }
  })
})
