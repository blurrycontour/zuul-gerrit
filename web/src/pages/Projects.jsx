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
import {
  Flex,
  FlexItem,
  Label,
  PageSection,
  PageSectionVariants,
  SearchInput,
  Title,
} from '@patternfly/react-core'

import { fetchProjectsIfNeeded,
         sortProjects,
         filterProjects
       } from '../actions/projects'
import { Fetchable } from '../containers/Fetching'

import {
  TableComposable,
  Thead,
  Tbody,
  Tr,
  Th,
  Td
} from '@patternfly/react-table'


class ProjectsPage extends React.PureComponent {
  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    isFetching: PropTypes.bool,
    sortIndex: PropTypes.number,
    sortDirection: PropTypes.string,
    projects: PropTypes.array,
    dispatch: PropTypes.func,
    table_columns: PropTypes.array,
    table_columns_descriptions: PropTypes.array,
    filterString: PropTypes.string
  }

  constructor(props) {
    super(props)
    /*
     * The SearchInput requires an onChange event that updates the
     * value property to show the X clearing box correctly.  Thus
     * we keep this value in state.
     */
    this.state = { filterString: this.props.filterString }
  }

  updateData = (force) => {
    this.props.dispatch(fetchProjectsIfNeeded(this.props.tenant, force))
  }

  componentDidMount () {
    document.title = 'Zuul Projects'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  onSort = (event, index, direction) => {
    this.props.dispatch(sortProjects(index, direction))
  }

  cellFormat = (field, project) => {
    if (field === 'name') {
      return (<Link to={this.props.tenant.linkPrefix + '/project/' + project.canonical_name}>
                {project.name}
              </Link>)
    } else if (field === 'builds') {
      return (<Link to={this.props.tenant.linkPrefix + '/builds?project=' + project.name}>
                Recent builds
              </Link>)
    } else if (field === 'type') {
      if (project.type === 'untrusted') {
        return (<Label color='orange'>untrusted</Label>)
      } else if (project.type === 'config') {
        return (<Label color='blue'>config</Label>)
      } else {
        return (<Label>{project.type}</Label>)
      }
    } else {
      return project[field]
    }
  }

  handleFilterStringChange = (value) => {
    /* We are only using this so that the search box gets an X when
     * somebody types something.  If we set the state for
     * every keypress, it results in calling render() constantly
     * which slows everything down.
     */
    if (this.state.filterString) {
      return
    }
    this.setState({
      filterString: value
    })
  }

  doFilter = (value, event, attrMap) => {
    if (!attrMap) {
      attrMap = {}
    }
    this.props.dispatch(filterProjects(attrMap, value))
  }

  clearFilter = () => {
    this.props.dispatch(filterProjects({}, ''))
    this.setState({filterString: ''})
  }

  render () {

    // When we are filtering, show the count of results
    let showCount = this.props.filterString ? this.props.projects.length : ''

    return (
      <React.Fragment>
        <PageSection variant={PageSectionVariants.light}>
          <Flex>
            <FlexItem>
              <Title headingLevel="h2">Project overview for {this.props.tenant.name}</Title>
            </FlexItem>
            <FlexItem align={{ default: 'alignRight' }}>
              <Fetchable
                isFetching={this.props.isFetching}
                fetchCallback={this.updateData}
              />
            </FlexItem>
          </Flex>
          <SearchInput
            placeholder='Filter projects'
            attributes = {[{attr:'connection_name', display:'Connection Type'},
                           {attr:'type', display:'Project type'}]}
            advancedSearchDelimiter='='
            value={this.state.filterString}
            onSearch={this.doFilter}
            onClear={this.clearFilter}
            onChange={this.handleFilterStringChange}
            resultsCount={showCount}
            className={['pf-u-w-50', 'pf-u-mb-sm']}
          />
          <TableComposable variant='compact'>
            <Thead>
              <Tr>
                {this.props.table_columns_descriptions.map((column, idx) => {
                  let sortParams = {}
                  if (column[1]) {
                    sortParams = {
                      sort: {
                        sortBy: {
                          index: this.props.sortIndex,
                          direction: this.props.sortDirection,
                        },
                        onSort: this.onSort,
                        columnIndex: idx
                      }
                    }
                  }
                  return(
                    <Th key={idx} {...sortParams}>{column[0]}</Th>
                  ) })
                }
              </Tr>
            </Thead>
            <Tbody>
              {this.props.projects.length === 0 && !this.props.isFetching &&
                <Tr key={1}><Td>No results match</Td></Tr>
              }
              {this.props.projects.map((row, rowIdx) => (
                <Tr key={rowIdx}>
                  {this.props.table_columns.map((colName, cellIdx) => (
                    <Td key={`${rowIdx}_${cellIdx}`}
                        dataLabel={this.props.table_columns_descriptions[cellIdx][0]}>
                      {this.cellFormat(colName, row)}
                    </Td>
                  ))}
                </Tr>
              ))}
            </Tbody>
          </TableComposable>
        </PageSection>
      </React.Fragment>
    )
  }
}

function selectProjects(state) {
  let projects = state.projects.projects
  let filterTerms = state.projects.filterTerms
  let termsCount = Object.keys(filterTerms).length
  /* nothing to filter, don't bother walking */
  if (termsCount === 0) {
    return projects
  }
  return projects.filter(function (project) {
    let results = []
    if (filterTerms.haswords) {
      results.push(project.name.includes(filterTerms.haswords))
    }
    if (filterTerms.connection_name) {
      results.push(project.connection_name === filterTerms.connection_name)
    }
    if (filterTerms.type) {
      results.push(project.type === filterTerms.type)
    }
    /* the results are all anded; if there's more than one they must
     * all match for a row to show
     */
    return results.every(e => e)
  })
}

function mapStateToProps(state) {
  return {
    tenant: state.tenant,
    isFetching: state.projects.isFetching,
    projects: selectProjects(state),
    sortDirection: state.projects.sortDirection,
    sortIndex: state.projects.sortIndex,
    filterTerms: state.projects.filterTerms,
    filterString: state.projects.filterString,
    table_columns: state.projects.table_columns,
    table_columns_descriptions: state.projects.table_columns_descriptions
  }
}

export default connect(mapStateToProps)(ProjectsPage)
