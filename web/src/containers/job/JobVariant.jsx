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
  Icon,
  ListView
} from 'patternfly-react'

import SourceContext from '../SourceContext'
import Nodeset from './Nodeset'
import Role from './Role'
import JobProject from './JobProject'


class JobVariant extends React.Component {
  static propTypes = {
    variant: PropTypes.object.isRequired,
    listRef: PropTypes.object,
    tenant: PropTypes.object
  }

  render () {
    const { tenant, listRef, variant } = this.props
    let title = variant.variant_description
    if (!title) {
      title = ''
      variant.branches.forEach((item) => {
        if (title) {
          title += ', '
        }
        title += item
      })
      if (title) {
        title = 'Branch: ' + title
      }
    }
    const rows = []
    const jobInfos = [
      'description',
      'parent', 'attempts', 'timeout', 'semaphore', 'implied_branch',
      'nodeset', 'variables',
    ]
    jobInfos.forEach(key => {
      let label = key
      let value = variant[key]

      if (!value) {
        return
      }

      if (label === 'nodeset') {
        value = <Nodeset nodeset={value} />
      }

      if (label === 'parent') {
        value = (
          <Link to={tenant.linkPrefix + '/job/' + value}>
            {value}
          </Link>
        )
      }
      if (label === 'variables') {
        value = (
          <span style={{whiteSpace: 'pre'}}>
            {JSON.stringify(value, undefined, 2)}
          </span>
        )
      }
      if (label === 'description') {
        value = (
          <span style={{whiteSpace: 'pre'}}>
            {value}
          </span>
        )
      }
      rows.push({label: label, value: value})
    })
    const jobInfosList = [
      'required_projects', 'dependencies', 'files', 'irrelevant_files', 'roles'
    ]
    jobInfosList.forEach(key => {
      let label = key
      let values = variant[key]

      if (values.length === 0) {
        return
      }
      const items = (
        <ul className='list-group'>
          {values.map((value, idx) => {
            let item
            if (label === 'required_projects') {
              item = <JobProject project={value} />
            } else if (label === 'roles') {
              item = <Role role={value} />
            } else {
              item = value
            }
            return (
              <li className='list-group-item' key={idx}>
                {item}
              </li>
            )
          })}
        </ul>
      )
      rows.push({label: label, value: items})
    })
    const AdditionalInfo = [(
      <ListView.InfoItem key={1}>
        <Icon
          type='pf'
          name={variant.voting ? 'connected' : 'disconnected'} />
        {variant.voting ? 'Voting' : 'Non-voting'}
      </ListView.InfoItem>
    )]
    if (variant.abstract) {
      AdditionalInfo.push(
        <ListView.InfoItem key={2}>
          <Icon type='pf' name='infrastructure' />
          Abstract
        </ListView.InfoItem>
      )
    }
    if (variant.final) {
      AdditionalInfo.push(
         <ListView.InfoItem key={3}>
          <Icon type='pf' name='infrastructure' />
          Final
        </ListView.InfoItem>
      )
    }
    if (variant.post_review) {
      AdditionalInfo.push(
        <ListView.InfoItem key={4}>
          <Icon type='pf' name='locked' />
          Post review
        </ListView.InfoItem>
      )
    }
    if (variant.protected) {
      AdditionalInfo.push(
        <ListView.InfoItem key={5}>
          <Icon type='pf' name='locked' />
          Protected
        </ListView.InfoItem>
      )
    }
    return (
      <ListView.Item
        hideCloseIcon={true}
        heading={(
          <p>{title} (<SourceContext context={variant.source_context}/>)</p>
        )}
        ref={listRef ? listRef : undefined}
        additionalInfo={AdditionalInfo}
        >
        <table className='table table-striped table-bordered'>
          <tbody>
            {rows.map(item => (
              <tr key={item.label}>
                <td>{item.label}</td>
                <td>{item.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ListView.Item>
    )
  }
}

export default connect(state => ({tenant: state.tenant}))(JobVariant)
