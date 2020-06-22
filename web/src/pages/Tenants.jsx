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

import * as React from 'react'
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import { Link } from 'react-router-dom'
import { Table } from 'patternfly-react'
import { _, t } from '../locales/utils'

import Refreshable from '../containers/Refreshable'
import { fetchTenantsIfNeeded } from '../actions/tenants'


class TenantsPage extends Refreshable {
  static propTypes = {
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData = (force) => {
    this.props.dispatch(fetchTenantsIfNeeded(force))
  }

  componentDidMount () {
    document.title = t('Zuul Tenants')
    this.updateData()
  }

  // TODO: fix Refreshable class to work with tenant less page.
  componentDidUpdate () { }

  render () {
    const { remoteData } = this.props
    const tenants = remoteData.tenants
    const headerFormat = value => <Table.Heading>{_(value)}</Table.Heading>
    const cellFormat = (value) => (
      <Table.Cell>{value}</Table.Cell>)
    const columns = []
    const myColumns = [
      'name', 'status', 'projects', 'jobs', 'builds', 'buildsets',
      'projects_count', 'queue']
    myColumns.forEach(column => {
      let prop = column
      let label = column.charAt(0).toUpperCase() + column.slice(1)
      if (column === 'projects_count') {
        label = 'Projects Count'
        prop = 'projects'
      } else if (column === 'projects') {
        prop = 'projects_link'
      }
      columns.push({
        header: {label: label,
          formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [cellFormat]}
      })
    })
    tenants.forEach(tenant => {
      tenant.status = (
        <Link to={'/t/' + tenant.name + '/status'}>{_('Status')}</Link>)
      tenant.projects_link = (
        <Link to={'/t/' + tenant.name + '/projects'}>{_('Projects')}</Link>)
      tenant.jobs = (
        <Link to={'/t/' + tenant.name + '/jobs'}>{_('Jobs')}</Link>)
      tenant.builds = (
        <Link to={'/t/' + tenant.name + '/builds'}>{_('Builds')}</Link>)
      tenant.buildsets = (
        <Link to={'/t/' + tenant.name + '/buildsets'}>{_('Buildsets')}</Link>)
    })
    return (
      <React.Fragment>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        <Table.PfProvider
          striped
          bordered
          hover
          columns={columns}
          >
          <Table.Header/>
          <Table.Body
            rows={tenants}
            rowKey="name"
            />
        </Table.PfProvider>
      </React.Fragment>
    )
  }
}

export default connect(state => ({remoteData: state.tenants}))(TenantsPage)
