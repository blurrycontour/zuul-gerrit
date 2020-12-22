// Copyright 2020 Red Hat, Inc
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
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import {
  EmptyState,
  EmptyStateBody,
  EmptyStateIcon,
  Spinner,
  Title,
} from '@patternfly/react-core'
import {
  OutlinedQuestionCircleIcon,
  PercentIcon,
  BuildIcon,
  CodeBranchIcon,
  CubeIcon,
  OutlinedClockIcon,
  LockIcon,
  TrashIcon,
  FingerprintIcon,
} from '@patternfly/react-icons'
import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
} from '@patternfly/react-table'
import { Link } from 'react-router-dom'
import * as moment from 'moment'

import { autohold_delete } from '../../api'
import { fetchAutoholdsIfNeeded } from '../../actions/autoholds'

import { IconProperty } from '../Misc'

function AutoholdTable(props) {
  const { autoholds, fetching, tenant, user, dispatch } = props
  const columns = [
    {
      title: <IconProperty icon={<FingerprintIcon />} value="ID" />,
      dataLabel: 'Request ID',
    },
    {
      title: <IconProperty icon={<CubeIcon />} value="Project" />,
      dataLabel: 'Project',
    },
    {
      title: <IconProperty icon={<BuildIcon />} value="Job" />,
      dataLabel: 'Job',
    },
    {
      title: <IconProperty icon={<CodeBranchIcon />} value="Ref Filter" />,
      dataLabel: 'Ref Filter',
    },
    {
      title: <IconProperty icon={<PercentIcon />} value="Count" />,
      dataLabel: 'Count',
    },
    {
      title: <IconProperty icon={<OutlinedQuestionCircleIcon />} value="Reason" />,
      dataLabel: 'Reason',
    },
    {
      title: <IconProperty icon={<OutlinedClockIcon />} value="Hold Duration" />,
      dataLabel: 'Hold Duration',
    },
    {
      title: '',
      dataLabel: 'Delete',
    }
  ]

  function handleAutoholdDelete(requestId) {
    autohold_delete(tenant.apiPrefix, requestId, user.token)
      .then(() => {
        alert('Autohold request deleted succesfully.')
        dispatch(fetchAutoholdsIfNeeded(tenant, true))
      })
      .catch(error => {
        alert(error)})
  }

  function renderAutoholdDeleteButton (requestId) {
    return (
      <TrashIcon
        title="Delete Autohold request"
        style={{cursor:'pointer'}}
        color='#A30000'
        onClick={(event) => {
          event.preventDefault()
          handleAutoholdDelete(requestId)
        }}/>
    )
  }

  function createAutoholdRow(autohold) {
    const count = autohold.current_count + '/' + autohold.max_count
    const node_expiration = moment.duration(autohold.node_expiration, 'seconds').humanize()
    const delete_button = (user.isAdmin && user.scope.indexOf(tenant.name) !== -1) ? renderAutoholdDeleteButton(autohold.id) : ''

    return {
      cells: [
        {
          title: (
            <>
              <span><Link to={`${tenant.linkPrefix}/autohold/${autohold.id}`}>{autohold.id}</Link></span>
            </>
          ),
        },
        {
          title: (
            <>
              <span>{autohold.project}</span>
            </>
          ),
        },
        {
          title: (
            <>
              <span>{autohold.job}</span>
            </>
          ),
        },
        {
          title: (
            <>
              <span>{autohold.ref_filter}</span>
            </>
          ),
        },
        {
          title: (
            <>
              <span>{count}</span>
            </>
          ),
        },
        {
          title: (
            <>
              <span>{autohold.reason}</span>
            </>
          ),
        },
        {
          title: (
            <>
              <span>{node_expiration}</span>
            </>
          ),
        },
        {
          title: (
            <>
              <span>{delete_button}</span>
            </>
          ),
        },
      ]
    }
  }

  function createFetchingRow() {
      const rows = [
        {
          heightAuto: true,
          cells: [
            {
              props: { colSpan: 8 },
              title: (
                <center>
                  <Spinner size="xl" />
                </center>
              ),
            },
          ],
        },
      ]
      return rows
    }

  let rows = []
  if (fetching) {
    rows = createFetchingRow()
    columns[0].dataLabel = ''
  } else {
    rows = autoholds.map((autohold) => createAutoholdRow(autohold))
  }

  return (
    <>
      <Table
        aria-label="Autohold Requests Table"
        variant={TableVariant.compact}
        cells={columns}
        rows={rows}
        className="zuul-autohold-table"
      >
        <TableHeader />
        <TableBody />
      </Table>

      {/* Show an empty state in case we don't have any autoholds but are also not
          fetching */}
      {!fetching && autoholds.length === 0 && (
        <EmptyState>
          <EmptyStateIcon icon={LockIcon} />
          <Title headingLevel="h1">No autohold requests found</Title>
          <EmptyStateBody>
            Nothing to display.
          </EmptyStateBody>
        </EmptyState>
      )}
    </>
  )
}

AutoholdTable.propTypes = {
  autoholds: PropTypes.array.isRequired,
  fetching: PropTypes.bool.isRequired,
  tenant: PropTypes.object,
  user: PropTypes.object,
  dispatch: PropTypes.func,
}

export default connect((state) => ({
  tenant: state.tenant,
  user: state.user,
}))(AutoholdTable)
