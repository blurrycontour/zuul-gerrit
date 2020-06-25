// Copyright 2019 Red Hat, Inc
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
import { Translate, I18n } from 'react-redux-i18n'

import { fetchBuildsets } from '../api'
import TableFilters from '../containers/TableFilters'


class BuildsetsPage extends TableFilters {
  static propTypes = {
    tenant: PropTypes.object
  }

  constructor () {
    super()

    this.prepareTableHeaders()
    this.state = {
      buildsets: null,
      currentFilterType: this.filterTypes[0],
      activeFilters: [],
      currentValue: ''
    }
  }

  updateData = (filters) => {
    let queryString = ''
    if (filters) {
      filters.forEach(item => queryString += '&' + item.key + '=' + item.value)
    }
    this.setState({buildsets: null})
    fetchBuildsets(this.props.tenant.apiPrefix, queryString).then(response => {
      this.setState({buildsets: response.data})
    })
  }

  componentDidMount () {
    document.title = I18n.t('buildsetsPage.title')
    if (this.props.tenant.name) {
      this.updateData(this.getFilterFromUrl())
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData(this.getFilterFromUrl())
    }
  }

  prepareTableHeaders() {
    const headerFormat = value => <Table.Heading><Translate value={'buildsetsPage.' + value} /></Table.Heading>
    const cellFormat = (value) => <Table.Cell>{value}</Table.Cell>
    const linkChangeFormat = (value, rowdata) => (
      <Table.Cell>
        <a href={rowdata.rowData.ref_url}>
          {value ?
           rowdata.rowData.change + ',' + rowdata.rowData.patchset :
           rowdata.rowData.newrev ?
             rowdata.rowData.newrev.substr(0, 7) :
           rowdata.rowData.branch}
        </a>
      </Table.Cell>
    )
    const linkBuildsetFormat = (value, rowdata) => (
      <Table.Cell title={I18n.t('buildsetsPage.' + value)}>
        <Link
          to={this.props.tenant.linkPrefix +
              '/buildset/' + rowdata.rowData.uuid}>
          {value}
        </Link>
      </Table.Cell>
    )
    this.columns = []
    this.filterTypes = []
    const myColumns = [
      'project',
      'branch',
      'pipeline',
      'change',
      'result']
    myColumns.forEach(column => {
      let prop = column
      let formatter = cellFormat
      if (column === 'change') {
        formatter = linkChangeFormat
      } else if (column === 'result') {
        formatter = linkBuildsetFormat
      }
      this.columns.push({
        header: {label: column, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
      if (column !== 'builds') {
        this.filterTypes.push({
          id: prop,
          title: I18n.t('buildsetsPage.' + column),
          placeholder: I18n.t('buildsetsPage.filterBy', {filter: I18n.t('buildsetsPage.' + column)}),
          filterType: 'text',
        })
      }
    })
    // Add buildset filter at the end
    this.filterTypes.push({
      id: 'uuid',
      title: I18n.t('buildsetsPage.buildset'),
      placeholder: I18n.t('buildsetsPage.filterByUUID'),
      filterType: 'text',
    })
  }

  renderTable (buildsets) {
    return (
      <Table.PfProvider
        striped
        bordered
        columns={this.columns}
      >
        <Table.Header/>
        <Table.Body
          rows={buildsets}
          rowKey='uuid'
          onRow={(row) => {
            switch (row.result) {
              case 'SUCCESS':
                return { className: 'success' }
              default:
                return { className: 'warning' }
            }
          }} />
      </Table.PfProvider>)
  }

  render() {
    const { buildsets } = this.state
    return (
      <React.Fragment>
        {this.renderFilter()}
        {buildsets ? this.renderTable(buildsets) : <p><Translate value="buildsetsPage.loading" /></p>}
      </React.Fragment>
    )
  }
}

export default connect(state => ({tenant: state.tenant}))(BuildsetsPage)
