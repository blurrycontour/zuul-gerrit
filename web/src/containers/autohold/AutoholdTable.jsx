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
} from '@patternfly/react-icons'
import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
} from '@patternfly/react-table'
import * as moment from 'moment'

import { IconProperty } from '../Misc'

function AutoholdTable(props) {
  const { autoholds, fetching } = props
  const columns = [
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
  ]

  function createAutoholdRow(autohold) {
    const count = autohold.current_count + '/' + autohold.max_count
    const node_expiration = moment.duration(autohold.node_expiration, 'seconds').humanize()

    return {
      cells: [
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
}

export default connect(() => ({
}))(AutoholdTable)
