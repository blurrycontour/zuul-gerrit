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

// The App is the parent component of every pages. Each page content is
// rendered by the Route object according to the current location.

import React from 'react'
import { matchPath, withRouter } from 'react-router'
import { Link, Redirect, Route, Switch } from 'react-router-dom'
import { connect } from 'react-redux'
import { Masthead } from 'patternfly-react'

import logo from './images/logo.png'
import { routes } from './routes'
import { store } from './reducers'

class App extends React.Component {
  constructor() {
    super()
    this.menu = routes()
  }
  renderMenu() {
    const { location } = this.props
    const activeItem = this.menu.find(
      item => location.pathname === item.to
    )
    let linkPrefix = ""
    if (this.defaultRoute === "/tenants") {
      // Multi-tenant, links need tenant prefix
      linkPrefix = "/t/" + this.tenant
    }
    return (
      <ul className="nav navbar-nav navbar-primary">
        {this.menu.filter(item => item.title).map(item => (
          <li key={item.to} className={item === activeItem ? 'active' : ''}>
            <Link to={linkPrefix + item.to}>{item.title}</Link>
          </li>
        ))}
      </ul>
    )
  }
  renderContent = () => {
    const allRoutes = []
    let routePrefix = ""
    if (this.defaultRoute === "/tenants") {
      // Multi-tenant, routes need a tenant prefix
      routePrefix = "/t/:tenant"
    }
    this.menu.map((item, index) => {
      allRoutes.push(
        <Route key={index} exact
               path={!item.globalRoute ? routePrefix + item.to : item.to}
               component={item.component} />
      )
      return allRoutes
    })
    return (
      <Switch>
        {allRoutes}
        <Redirect from="*" to={this.defaultRoute}
                  key="default-route" />
      </Switch>
    )
  }
  setTenant(name) {
    this.tenant = name
    return {
      type: 'SET_TENANT',
      name
    }
  }
  render() {
    const match = matchPath(this.props.location.pathname,
                            {path: '/t/:tenant'})
    let tenant = ""
    if (match) {
      tenant = match.params.tenant
    }
    const { info } = this.props
    if (info.capabilities) {
      if (info.tenant) {
        // White label
        this.defaultRoute = "/status"
        tenant = info.tenant
      } else if (!info.tenant) {
        // Multi tenant
        this.defaultRoute = "/tenants"
      }
    } else {
      return (<h2>Loading...</h2>)
    }
    // Store the selected/discovered tenant name in the store,
    // the api module uses info.tenant and tenant name to resolve api urls.
    store.dispatch(this.setTenant(tenant))

    return (
      <React.Fragment>
        <Masthead
          iconImg={logo}
          navToggle
          thin
          >
          <div className="collapse navbar-collapse">
            {tenant ? this.renderMenu() : ''}
            <ul className="nav navbar-nav navbar-utility">
              <li><a href="https://zuul-ci.org/docs"
                     rel="noopener noreferrer" target="_blank">
                  Documentation
              </a></li>
              {tenant ? (
                <li><Link to={this.defaultRoute}>
                    <strong>Tenant</strong> {tenant}
                </Link></li>): ""}
            </ul>
          </div>
        </Masthead>
        <div className="container-fluid container-cards-pf">
          {this.renderContent()}
        </div>
      </React.Fragment>
    )
  }
}

// This connect the info state from the store to the info property of the App.
const mapStateToProps = (state, ownProps) => {
  return {
    info: state.info
  }
}

const mapDispatchToProps = (dispatch) => {
  return {}
}

export default withRouter(connect(mapStateToProps, mapDispatchToProps)(App))
