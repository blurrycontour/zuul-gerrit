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
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { Link } from 'react-router-dom'
import { Table } from 'patternfly-react'
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { _, t } from '../locales/utils'

import { fetchProjectsIfNeeded } from '../actions/projects'
import { Fetchable, Fetching } from '../containers/Fetching'


class ProjectsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData = (force) => {
    this.props.dispatch(fetchProjectsIfNeeded(this.props.tenant, force))
  }

  componentDidMount () {
    document.title = t('Zuul Projects')
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  render () {
    const { remoteData } = this.props
    const projects = remoteData.projects[this.props.tenant.name]

    // TODO (felix): Can we somehow differentiate between "no projects yet" (due
    // to fetching) and "no projects at all", so we could show an empty state
    // in the latter case. The same applies for other pages like labels, nodes,
    // buildsets, ... as well.
    if (!projects) {
      return <Fetching />
    }

    const headerFormat = value => <Table.Heading>{_(value)}</Table.Heading>
    const cellFormat = (value) => (
      <Table.Cell>{value}</Table.Cell>)
    const cellProjectFormat = (value, row) => (
      <Table.Cell>
        <Link to={this.props.tenant.linkPrefix + '/project/' + row.rowData.canonical_name}>
          {value}
        </Link>
      </Table.Cell>)
    const cellBuildFormat = (value) => (
      <Table.Cell>
        <Link to={this.props.tenant.linkPrefix + '/builds?project=' + value}>
          builds
        </Link>
      </Table.Cell>)
      const cellTypeFormat = (value) => (
        <Table.Cell title={t(value)} >{value}</Table.Cell>)
    const columns = []
    const myColumns = ['name', 'connection', 'type', 'last builds']
    myColumns.forEach(column => {
      let formatter = cellFormat
      let prop = column
      if (column === 'name') {
        formatter = cellProjectFormat
      }
      if (column === 'type') {
        formatter = cellTypeFormat
      }
      if (column === 'connection') {
        prop = 'connection_name'
      }
      if (column === 'last builds') {
        prop = 'name'
        formatter = cellBuildFormat
      }
      columns.push({
        header: {label: column,
          formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
    })
    return (
      <PageSection variant={PageSectionVariants.light}>
        <PageSection style={{paddingRight: '5px'}}>
          <Fetchable
            isFetching={remoteData.isFetching}
            fetchCallback={this.updateData}
          />
        </PageSection>
        <Table.PfProvider
          striped
          bordered
          hover
          columns={columns}
        >
          <Table.Header/>
          <Table.Body
            rows={projects}
            rowKey="name"
          />
        </Table.PfProvider>
      </PageSection>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.projects,
}))(ProjectsPage)
