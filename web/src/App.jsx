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
import { Link, NavLink, Redirect, Route, Switch } from 'react-router-dom'
import { connect } from 'react-redux'
import {
  TimedToastNotification,
  ToastNotificationList,
} from 'patternfly-react'
import * as moment from 'moment'
import {
  Brand,
  Button,
  ButtonVariant,
  Dropdown,
  DropdownItem,
  DropdownToggle,
  DropdownSeparator,
  KebabToggle,
  Modal,
  Nav,
  NavItem,
  NavList,
  NotificationBadge,
  NotificationDrawer,
  NotificationDrawerBody,
  NotificationDrawerList,
  NotificationDrawerListItem,
  NotificationDrawerListItemBody,
  NotificationDrawerListItemHeader,
  Page,
  PageHeader,
  PageHeaderTools,
  PageHeaderToolsGroup,
  PageHeaderToolsItem,
} from '@patternfly/react-core'

import {
  BellIcon,
  BookIcon,
  CodeIcon,
  UsersIcon,
} from '@patternfly/react-icons'
import ChevronDownIcon from '@patternfly/react-icons/dist/esm/icons/chevron-down-icon'

import ErrorBoundary from './containers/ErrorBoundary'
import { Fetching } from './containers/Fetching'
import SelectTz from './containers/timezone/SelectTz'
import ConfigModal from './containers/config/Config'
import logo from './images/logo.svg'
import { clearError } from './actions/errors'
import { fetchConfigErrorsAction } from './actions/configErrors'
import { fetchTenantsIfNeeded } from './actions/tenants'
import { routes } from './routes'
import { setTenantAction } from './actions/tenant'

class App extends React.Component {
  static propTypes = {
    errors: PropTypes.array,
    configErrors: PropTypes.array,
    info: PropTypes.object,
    tenant: PropTypes.object,
    tenants: PropTypes.object,
    timezone: PropTypes.string,
    location: PropTypes.object,
    history: PropTypes.object,
    dispatch: PropTypes.func,
    isKebabDropdownOpen: PropTypes.bool,
  }

  state = {
    showErrors: false,
    isTenantDropdownOpen: false,
  }

  renderMenu() {
    const { tenant } = this.props
    if (tenant.name) {
      return (
        <Nav aria-label="Nav" variant="horizontal">
          <NavList>
            {this.menu.filter(item => item.title).map(item => (
              <NavItem itemId={item.to} key={item.to}>
                <NavLink
                  to={tenant.linkPrefix + item.to}
                  activeClassName="pf-c-nav__link pf-m-current"
                >
                  {item.title}
                </NavLink>
              </NavItem>
            ))}
          </NavList>
        </Nav>
      )
    } else {
      // Return an empty navigation bar in case we don't have an active tenant
      return <Nav aria-label="Nav" variant="horizontal" />
    }
  }

  renderContent = () => {
    const { info, tenant } = this.props
    const allRoutes = []

    if (info.isFetching) {
      return <Fetching />
    }
    this.menu
      // Do not include '/tenants' route in white-label setup
      .filter(item =>
        (tenant.whiteLabel && !item.globalRoute) || !tenant.whiteLabel)
      .forEach((item, index) => {
        // We use react-router's render function to be able to pass custom props
        // to our route components (pages):
        // https://reactrouter.com/web/api/Route/render-func
        // https://learnwithparam.com/blog/how-to-pass-props-in-react-router/
        allRoutes.push(
          <Route
            key={index}
            path={
              item.globalRoute ? item.to :
                item.noTenantPrefix ? item.to : tenant.routePrefix + item.to}
            render={routerProps => (
              <item.component {...item.props} {...routerProps} />
            )}
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
        this.props.dispatch(fetchTenantsIfNeeded())

        const match = matchPath(
          this.props.location.pathname, { path: '/t/:tenant' })

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

  constructor() {
    super()
    this.menu = routes()
  }

  handleKebabDropdownToggle = (isKebabDropdownOpen) => {
    this.setState({
      isKebabDropdownOpen
    })
  }

  handleKebabDropdownSelect = () => {
    this.setState({
      isKebabDropdownOpen: !this.state.isKebabDropdownOpen
    })
  }

  handleApiLink = () => {
    const { history } = this.props
    history.push('/openapi')
  }

  handleDocumentationLink = () => {
    window.open('https://zuul-ci.org/docs', '_blank', 'noopener noreferrer')
  }

  handleTenantLink = () => {
    const { history, tenant } = this.props
    history.push(tenant.defaultRoute)
  }

  handleModalClose = () => {
    this.setState({
      showErrors: false
    })
  }

  renderErrors = (errors) => {
    return (
      <ToastNotificationList>
        {errors.map(error => (
          <TimedToastNotification
            key={error.id}
            type='error'
            onDismiss={() => { this.props.dispatch(clearError(error.id)) }}
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
    const { showErrors } = this.state
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
        <NotificationDrawerListItem
          key={idx}
          variant="danger"
          onClick={() => {
            history.push(this.props.tenant.linkPrefix + '/config-errors')
            this.setState({ showErrors: false })
          }}
        >
          <NotificationDrawerListItemHeader
            title={item.source_context.project + ' | ' + ctxPath}
            variant="danger" />
          <NotificationDrawerListItemBody>
            <pre style={{ whiteSpace: 'pre-wrap' }}>
              {error}
            </pre>
          </NotificationDrawerListItemBody>
        </NotificationDrawerListItem>
      )
    })

    return (
      <Modal
        isOpen={showErrors}
        onClose={this.handleModalClose}
        aria-label="Config Errors"
        header={
          <>
            <span className="zuul-config-errors-title">
              Config Errors
            </span>
            <span className="zuul-config-errors-count">
              {errors.length} error(s)
            </span>
          </>
        }
      >
        <NotificationDrawer>
          <NotificationDrawerBody>
            <NotificationDrawerList>
              {errors.map(item => (item))}
            </NotificationDrawerList>
          </NotificationDrawerBody>
        </NotificationDrawer>
      </Modal>
    )
  }

  renderTenantDropdown() {
    const { tenant, tenants } = this.props
    const { isTenantDropdownOpen } = this.state

    if (tenant.whiteLabel) {
      return (
        <PageHeaderToolsItem>
          <strong>Tenant</strong> {tenant.name}
        </PageHeaderToolsItem>
      )
    } else {
      const tenantLink = (_tenant) => {
        const currentPath = this.props.location.pathname
        let suffix
        switch (currentPath) {
          case '/t/' + tenant.name + '/projects':
            suffix = '/projects'
            break
          case '/t/' + tenant.name + '/jobs':
            suffix = '/jobs'
            break
          case '/t/' + tenant.name + '/labels':
            suffix = '/labels'
            break
          case '/t/' + tenant.name + '/nodes':
            suffix = '/nodes'
            break
          case '/t/' + tenant.name + '/builds':
            suffix = '/builds'
            break
          case '/t/' + tenant.name + '/buildsets':
            suffix = '/buildsets'
            break
          case '/t/' + tenant.name + '/status':
          default:
            // all other paths point to tenant-specific resources that would most likely result in a 404
            suffix = '/status'
            break
        }
        return <Link to={'/t/' + _tenant.name + suffix}>{_tenant.name}</Link>
      }

      const options = tenants.tenants.filter(
        (_tenant) => (_tenant.name !== tenant.name)
      ).map(
        (_tenant, idx) => {
          return (
            <DropdownItem key={'tenant-dropdown-' + idx} component={tenantLink(_tenant)} />
          )
        })
      options.push(
        <DropdownSeparator key="tenant-dropdown-separator" />,
        <DropdownItem
          key="tenant-dropdown-tenants_page"
          component={<Link to={tenant.defaultRoute}>Go to tenants page</Link>} />
      )

      return (tenants.isFetching ?
        <PageHeaderToolsItem>
          Loading tenants ...
        </PageHeaderToolsItem> :
        <>
          <PageHeaderToolsItem>
            <Dropdown
              isOpen={isTenantDropdownOpen}
              toggle={
                <DropdownToggle
                  className={`zuul-tenant-dropdown-toggle${isTenantDropdownOpen ? '-expanded' : ''}`}
                  id="tenant-dropdown-toggle-id"
                  onToggle={(isOpen) => { this.setState({ isTenantDropdownOpen: isOpen }) }}
                  toggleIndicator={ChevronDownIcon}
                >
                  <strong>Tenant</strong> {tenant.name}
                </DropdownToggle>}
              onSelect={() => { this.setState({ isTenantDropdownOpen: !isTenantDropdownOpen }) }}
              dropdownItems={options}
            />
          </PageHeaderToolsItem>
        </>)
    }
  }

  render() {
    const { isKebabDropdownOpen } = this.state
    const { errors, configErrors, tenant } = this.props

    const nav = this.renderMenu()

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

    if (tenant.name) {
      kebabDropdownItems.push(
        <DropdownItem
          key="tenant"
          onClick={event => this.handleTenantLink(event)}
        >
          <UsersIcon /> Tenants
        </DropdownItem>
      )
    }

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
          {tenant.name && (this.renderTenantDropdown())}
        </PageHeaderToolsGroup>
        <PageHeaderToolsGroup>
          {/* this kebab dropdown replaces the icon buttons and is hidden for
              desktop sizes */}
          <PageHeaderToolsItem visibility={{ lg: 'hidden' }}>
            <Dropdown
              isPlain
              position="right"
              onSelect={this.handleKebabDropdownSelect}
              toggle={<KebabToggle onToggle={this.handleKebabDropdownToggle} />}
              isOpen={isKebabDropdownOpen}
              dropdownItems={kebabDropdownItems}
            />
          </PageHeaderToolsItem>
        </PageHeaderToolsGroup>
        {configErrors.length > 0 &&
          <NotificationBadge
            isRead={false}
            aria-label="Notifications"
            onClick={(e) => {
              e.preventDefault()
              this.setState({ showErrors: !this.state.showErrors })
            }}
          >
            <BellIcon />
          </NotificationBadge>
        }
        <SelectTz />
        <ConfigModal />
      </PageHeaderTools>
    )

    // In case we don't have an active tenant, fall back to the root URL
    const logoUrl = tenant.name ? tenant.defaultRoute : '/'
    const pageHeader = (
      <PageHeader
        logo={<Brand src={logo} alt='Zuul logo' className="zuul-brand" />}
        logoProps={{ to: logoUrl }}
        logoComponent={Link}
        headerTools={pageHeaderTools}
        topNav={nav}
      />
    )

    return (
      <React.Fragment>
        {errors.length > 0 && this.renderErrors(errors)}
        {this.renderConfigErrors(configErrors)}
        <Page header={pageHeader}>
          <ErrorBoundary>
            {this.renderContent()}
          </ErrorBoundary>
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
    tenants: state.tenants,
    timezone: state.timezone
  })
)(App))
