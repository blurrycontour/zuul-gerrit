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
import PropTypes from 'prop-types'
import { matchPath, withRouter } from 'react-router'
import { Link, Redirect, Route, Switch } from 'react-router-dom'
import { connect } from 'react-redux'
import {
  Icon,
  Notification,
  NotificationDrawer,
  TimedToastNotification,
  ToastNotificationList,
} from 'patternfly-react'
import * as moment from 'moment'

import ErrorBoundary from './containers/ErrorBoundary'
import SelectTz from './containers/timezone/SelectTz'
import logo from './images/logo.png'
import { clearError } from './actions/errors'
import { fetchConfigErrorsAction } from './actions/configErrors'
import { routes } from './routes'
import { setTenantAction } from './actions/tenant'

import {
  Brand,
  Button,
  ButtonVariant,
  Dropdown,
  DropdownItem,
  KebabToggle,
  Nav,
  NavItem,
  NavList,
  Page,
  PageHeader,
  PageHeaderTools,
  PageHeaderToolsGroup,
  PageHeaderToolsItem,
  PageSection,
  PageSectionVariants,
} from '@patternfly/react-core';

import { BookIcon, CodeIcon, UsersIcon } from '@patternfly/react-icons';

class App extends React.Component {
  static propTypes = {
    errors: PropTypes.array,
    configErrors: PropTypes.array,
    info: PropTypes.object,
    tenant: PropTypes.object,
    timezone: PropTypes.string,
    location: PropTypes.object,
    history: PropTypes.object,
    dispatch: PropTypes.func,
    isKebabDropdownOpen: false,
  }

  state = {
    menuCollapsed: true,
    showErrors: false
  }

  onNavToggleClick = () => {
    this.setState({
      menuCollapsed: !this.state.menuCollapsed
    })
  }

  onNavClick = () => {
    this.setState({
      menuCollapsed: true
    })
  }

  onKebabDropdownToggle = (isKebabDropdownOpen) => {
    this.setState({
      isKebabDropdownOpen
    });
  };

  onKebabDropdownSelect = (event) => {
    this.setState({
      isKebabDropdownOpen: !this.state.isKebabDropdownOpen
    });
  };

  constructor() {
    super()
    this.menu = routes()
  }

  renderMenu() {
    const { location } = this.props
    const activeItem = this.menu.find(
      item => location.pathname === item.to
    )
    return (
      <Nav aria-label="Nav" variant="horizontal">
        <NavList>
          {this.menu.filter(item => item.title).map(item => (
            <NavItem
              itemId={item.to}
              key={item.to}
              isActive={item === activeItem}
            >
              <Link
                to={this.props.tenant.linkPrefix + item.to}
                onClick={this.onNavClick}
              >
                {item.title}
              </Link>
            </NavItem>
          ))}
        </NavList>
      </Nav>
    )
  }

  renderContent = () => {
    const { info, tenant } = this.props
    const allRoutes = []

    if (info.isFetching) {
      return (<h2>Fetching info...</h2>)
    }
    this.menu
      // Do not include '/tenants' route in white-label setup
      .filter(item =>
              (tenant.whiteLabel && !item.globalRoute) || !tenant.whiteLabel)
      .forEach((item, index) => {
        allRoutes.push(
          <Route
            key={index}
            path={
              item.globalRoute ? item.to :
                item.noTenantPrefix ? item.to : tenant.routePrefix + item.to}
            component={item.component}
            exact
            />
        )
    })
    if (tenant.defaultRoute)
      allRoutes.push(
        <Redirect from='*' to={tenant.defaultRoute} key='default-route' />
      )
    return (
      <Switch>
        {allRoutes}
      </Switch>
    )
  }

  componentDidUpdate() {
    // This method is called when info property is updated
    const { tenant, info } = this.props
    if (info.ready) {
      let tenantName, whiteLabel

      if (info.tenant) {
        // White label
        whiteLabel = true
        tenantName = info.tenant
      } else if (!info.tenant) {
        // Multi tenant, look for tenant name in url
        whiteLabel = false

        const match = matchPath(
          this.props.location.pathname, {path: '/t/:tenant'})

        if (match) {
          tenantName = match.params.tenant
        }
      }
      // Set tenant only if it changed to prevent DidUpdate loop
      if (tenant.name !== tenantName) {
        const tenantAction = setTenantAction(tenantName, whiteLabel)
        this.props.dispatch(tenantAction)
        if (tenantName) {
          this.props.dispatch(fetchConfigErrorsAction(tenantAction.tenant))
        }
      }
    }
  }

  renderErrors = (errors) => {
    return (
      <ToastNotificationList>
        {errors.map(error => (
         <TimedToastNotification
             key={error.id}
             type='error'
             onDismiss={() => {this.props.dispatch(clearError(error.id))}}
             >
           <span title={moment.utc(error.date).tz(this.props.timezone).format()}>
               <strong>{error.text}</strong> ({error.status})&nbsp;
                   {error.url}
             </span>
         </TimedToastNotification>
        ))}
      </ToastNotificationList>
    )
  }

  renderConfigErrors = (configErrors) => {
    const { history } = this.props
    const errors = []
    configErrors.forEach((item, idx) => {
      let error = item.error
      let cookie = error.indexOf('The error was:')
      if (cookie !== -1) {
        error = error.slice(cookie + 18).split('\n')[0]
      }
      let ctxPath = item.source_context.path
      if (item.source_context.branch !== 'master') {
        ctxPath += ' (' + item.source_context.branch + ')'
      }
      errors.push(
        <Notification
          key={idx}
          seen={false}
          onClick={() => {
            history.push(this.props.tenant.linkPrefix + '/config-errors')
            this.setState({showErrors: false})
          }}
          >
          <Icon className='pull-left' type='pf' name='error-circle-o' />
          <Notification.Content>
            <Notification.Message>
              {error}
            </Notification.Message>
            <Notification.Info
              leftText={item.source_context.project}
              rightText={ctxPath}
              />
          </Notification.Content>
        </Notification>
      )
    })
    return (
      <NotificationDrawer style={{minWidth: '500px'}}>
      <NotificationDrawer.Panel>
        <NotificationDrawer.PanelHeading>
          <NotificationDrawer.PanelTitle>
            Config Errors
          </NotificationDrawer.PanelTitle>
          <NotificationDrawer.PanelCounter
            text={errors.length + ' error(s)'} />
        </NotificationDrawer.PanelHeading>
        <NotificationDrawer.PanelCollapse id={1} collapseIn>
          <NotificationDrawer.PanelBody key='containsNotifications'>
            {errors.map(item => (item))}
          </NotificationDrawer.PanelBody>

        </NotificationDrawer.PanelCollapse>
        </NotificationDrawer.Panel>
      </NotificationDrawer>
    )
  }

  handleApiLink = (event) => {
    const { history } = this.props;
    history.push('/openapi');
  }

  handleDocumentationLink = (event) => {
    window.open('https://zuul-ci.org/docs', '_blank', 'noopener noreferrer');
  }

  handleTenantLink = (event) => {
    const { history, tenant } = this.props;
    history.push(tenant.defaultRoute);
  }

  render() {
    const { isKebabDropdownOpen, menuCollapsed, showErrors } = this.state
    const { errors, configErrors, tenant } = this.props

    const nav = this.renderMenu();

    const kebabDropdownItems = [
      <DropdownItem key="api" onClick={event => this.handleApiLink(event)}>
        <CodeIcon /> API
      </DropdownItem>,
      <DropdownItem
        key="documentation"
        onClick={event => this.handleDocumentationLink(event)}
      >
        <BookIcon /> Documentation
      </DropdownItem>,
    ]

    {tenant.name && (
      kebabDropdownItems.push(
        <DropdownItem
          key="tenant"
          onClick={event => this.handleTenantLink(event)}
        >
          <UsersIcon /> Tenant
        </DropdownItem>
      )
    )}

    const pageHeaderTools = (
      <PageHeaderTools>
        {/* The utility navbar is only visible on desktop sizes
            and replaced by a kebab dropdown for smaller sizes */}
        <PageHeaderToolsGroup
          visibility={{ default: 'hidden', lg: 'visible' }}
        >
          <PageHeaderToolsItem>
            <Link to='/openapi'>
              <Button variant={ButtonVariant.plain}>
                <CodeIcon /> API
              </Button>
            </Link>
          </PageHeaderToolsItem>
          <PageHeaderToolsItem>
            <a
              href='https://zuul-ci.org/docs'
              rel='noopener noreferrer'
              target='_blank'
            >
              <Button variant={ButtonVariant.plain}>
                <BookIcon /> Documentation
              </Button>
            </a>
          </PageHeaderToolsItem>
          {tenant.name && (
            <PageHeaderToolsItem>
              <Link to={tenant.defaultRoute}>
                <Button variant={ButtonVariant.plain}>
                  <strong>Tenant</strong> {tenant.name}
                </Button>
              </Link>
            </PageHeaderToolsItem>
          )}
        </PageHeaderToolsGroup>
        <PageHeaderToolsGroup>
          <PageHeaderToolsItem visibility={{ lg: 'hidden' }} /** this kebab dropdown replaces the icon buttons and is hidden for desktop sizes */>
            <Dropdown
              isPlain
              position="right"
              onSelect={this.onKebabDropdownSelect}
              toggle={<KebabToggle onToggle={this.onKebabDropdownToggle} />}
              isOpen={isKebabDropdownOpen}
              dropdownItems={kebabDropdownItems}
            />
          </PageHeaderToolsItem>
        </PageHeaderToolsGroup>
        <SelectTz/>
      </PageHeaderTools>
    );

    const pageHeader = (
      <PageHeader
        logo={<Brand src={logo} alt='Zuul logo' />}
        headerTools={pageHeaderTools}
        topNav={nav}
      />
    );

    return (
      <React.Fragment>
        {/* TODO (felix): NotificationDrawer + Toggle */}
        {/*
          <div className='collapse navbar-collapse'>
            {tenant.name && this.renderMenu()}
            <ul className='nav navbar-nav navbar-utility'>
              { configErrors.length > 0 &&
                <NotificationDrawer.Toggle
                  className="zuul-config-errors"
                  hasUnreadMessages
                  style={{color: 'orange'}}
                  onClick={(e) => {
                    e.preventDefault()
                    this.setState({showErrors: !this.state.showErrors})}}
                  />
              }
          </div>
        */}
        {errors.length > 0 && this.renderErrors(errors)}
        <Page header={pageHeader}>
          <PageSection variant={PageSectionVariants.light}>
            <ErrorBoundary>
              {this.renderContent()}
            </ErrorBoundary>
          </PageSection>
        </Page>
      </React.Fragment>
    )
  }
}

// This connect the info state from the store to the info property of the App.
export default withRouter(connect(
  state => ({
    errors: state.errors,
    configErrors: state.configErrors,
    info: state.info,
    tenant: state.tenant,
    timezone: state.timezone
  })
)(App))
