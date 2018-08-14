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
import { matchPath, withRouter } from 'react-router';
import { Link, Redirect, Route, Switch } from 'react-router-dom';
import { connect } from 'react-redux';
import { Masthead } from 'patternfly-react';

import logo from './images/logo.png';
import { routes } from './routes';

class App extends React.Component {
  constructor() {
    super();
    this.menu = routes();
  }
  renderMenu() {
    const { location } = this.props;
    const activeItem = this.menu.find(
      item => location.pathname === item.to
    );
    let linkPrefix = "";
    if (this.defaultRoute === "/tenants") {
      linkPrefix = "/t/" + this.tenant;
    }
    return (
      <ul className="nav navbar-nav navbar-primary">
        {this.menu.filter(item => item.title).map(item => (
          <li key={item.to} className={item === activeItem ? 'active' : ''}>
            <Link to={linkPrefix + item.to}>{item.title}</Link>
          </li>
        ))}
      </ul>
    );
  }
  renderContent = () => {
    const allRoutes = [];
    let routePrefix = "";
    if (this.defaultRoute === "/tenants") {
      routePrefix = "/t/:tenant";
    }
    this.menu.map((item, index) => {
      allRoutes.push(
        <Route key={index} exact
               path={item.title ? routePrefix + item.to : item.to}
               component={item.component} />
      );
      return allRoutes;
    });
    return (
      <Switch>
        {allRoutes}
        <Redirect from="*" to={this.defaultRoute}
                  key="default-route" />
      </Switch>
    );
  };

  render() {
    const match = matchPath(this.props.location.pathname,
                            {path: '/t/:tenant'});
    if (match) {
      this.tenant = match.params.tenant;
    } else {
      this.tenant = "";
    }
    const { info } = this.props;
    if (info.length !== 0 && info.tenant) {
      this.defaultRoute = "/status";
      this.tenant = info.tenant;
    } else if (info.length !== 0 && !info.tenant) {
      this.defaultRoute = "/tenants";
    } else {
      this.defaultRoute = "/";
    }

    return (
      <React.Fragment>
        <Masthead
          iconImg={logo}
          navToggle
          thin
          >
          {this.tenant ? this.renderMenu() : ''}
          <ul className="nav navbar-nav navbar-utility">
            <li><a href="https://zuul-ci.org/docs"
                   rel="noopener noreferrer" target="_blank">
                Documentation
            </a></li>
            {this.tenant ? (
              <li><Link to={this.defaultRoute}>
                <strong>Tenant</strong> {this.tenant}
              </Link></li>): ""}
          </ul>
        </Masthead>
        <div className="container" style={{width: '100%', marginTop: '10px'}}>
          {this.renderContent()}
        </div>
      </React.Fragment>
    );
  }
}

const mapStateToProps = (state, ownProps) => {
  return {
    info: state.info
  };
};

const mapDispatchToProps = (dispatch) => {
  return {};
};

export default withRouter(connect(mapStateToProps, mapDispatchToProps)(App));
