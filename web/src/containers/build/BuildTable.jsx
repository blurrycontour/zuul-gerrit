// Copyright 2020 BMW Group
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
import { Link } from 'react-router-dom'
import {
  Button,
  EmptyState,
  EmptyStateBody,
  EmptyStateIcon,
  EmptyStateSecondaryActions,
  Spinner,
  Title,
} from '@patternfly/react-core'
import {
  BuildIcon,
  CodeBranchIcon,
  CodeIcon,
  CubeIcon,
  OutlinedCalendarAltIcon,
  OutlinedClockIcon,
  PollIcon,
  StreamIcon,
} from '@patternfly/react-icons'
import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
} from '@patternfly/react-table'
import 'moment-duration-format'
import * as moment from 'moment'

import { BuildResult, BuildResultWithIcon, IconProperty } from './Misc'
import { ExternalLink } from '../../Misc'

function BuildTable(props) {
  const { builds, fetching, onClearFilters, tenant, timezone } = props
  const columns = [
    {
      title: <IconProperty icon={<BuildIcon />} value="Job" />,
      dataLabel: 'Job',
    },
    {
      title: <IconProperty icon={<CubeIcon />} value="Project" />,
      dataLabel: 'Project',
    },
    {
      title: <IconProperty icon={<CodeBranchIcon />} value="Branch" />,
      dataLabel: 'Branch',
    },
    {
      title: <IconProperty icon={<StreamIcon />} value="Pipeline" />,
      dataLabel: 'Pipeline',
    },
    {
      title: <IconProperty icon={<CodeIcon />} value="Change" />,
      dataLabel: 'Change',
    },
    {
      title: <IconProperty icon={<OutlinedClockIcon />} value="Duration" />,
      dataLabel: 'Duration',
    },
    {
      title: (
        <IconProperty icon={<OutlinedCalendarAltIcon />} value="Start time" />
      ),
      dataLabel: 'Start time',
    },
    {
      title: <IconProperty icon={<PollIcon />} value="Result" />,
      dataLabel: 'Result',
    },
  ]

  function createBuildRow(build) {
    // This link will be defined on each cell of the current row as this is the
    // only way to define a valid HTML link on a table row. Although we could
    // simply define an onClick handler on the whole row and programatically
    // switch to the buildresult page, this wouldn't provide the same
    // look-and-feel as a plain HTML link.
    const buildResultLink = (
      <Link
        to={`${tenant.linkPrefix}/build/${build.uuid}`}
        className="zuul-stretched-link"
      />
    )
    return {
      cells: [
        {
          // To allow passing anything else than simple string values to a table
          // cell, we must use the title attribute.
          title: (
            <>
              {buildResultLink}
              <BuildResultWithIcon result={build.result} colored={build.voting}>
                {build.job_name}
                {!build.voting && ' (non-voting)'}
              </BuildResultWithIcon>
            </>
          ),
        },
        {
          title: (
            <>
              {buildResultLink}
              <span>{build.project}</span>
            </>
          ),
        },
        {
          title: (
            <>
              {buildResultLink}
              <span>{build.branch ? build.branch : build.ref}</span>
            </>
          ),
        },
        {
          title: (
            <>
              {buildResultLink}
              <span>{build.pipeline}</span>
            </>
          ),
        },
        {
          title: (
            <>
              {buildResultLink}
              {build.change && (
                <span style={{ zIndex: 1, position: 'relative' }}>
                  <ExternalLink target={build.ref_url}>
                    {build.change},{build.patchset}
                  </ExternalLink>
                </span>
              )}
            </>
          ),
        },
        {
          title: (
            <>
              {buildResultLink}
              <span>
                {moment
                  .duration(build.duration, 'seconds')
                  .format('h [hr] m [min] s [sec]')}
              </span>
            </>
          ),
        },
        {
          title: (
            <>
              {buildResultLink}
              <span>
                {moment
                  .utc(build.start_time)
                  .tz(timezone)
                  .format('YYYY-MM-DD HH:mm:ss')}
              </span>
            </>
          ),
        },
        {
          title: (
            <>
              {buildResultLink}
              <BuildResult result={build.result} colored={build.voting} />
            </>
          ),
        },
      ],
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
    // The dataLabel property is used to show the column header in a list-like
    // format for smaller viewports. When we are fetching, we don't want the
    // fetching row to be prepended by a "Job" column header. The other column
    // headers are not relevant here since we only have a single cell in the
    // fetcihng row.
    columns[0].dataLabel = ''
  } else {
    rows = builds.map((build) => createBuildRow(build))
  }

  return (
    <>
      <Table
        aria-label="Builds Table"
        variant={TableVariant.compact}
        cells={columns}
        rows={rows}
        className="zuul-build-table"
      >
        <TableHeader />
        <TableBody />
      </Table>

      {/* Show an empty state in case we don't have any builds but are also not
          fetching */}
      {!fetching && builds.length === 0 && (
        <EmptyState>
          <EmptyStateIcon icon={BuildIcon} />
          <Title headingLevel="h1">No builds found</Title>
          <EmptyStateBody>
            No builds match this filter criteria. Remove some filters or clear
            all to show results.
          </EmptyStateBody>
          <EmptyStateSecondaryActions>
            <Button variant="link" onClick={onClearFilters}>
              Clear all filters
            </Button>
          </EmptyStateSecondaryActions>
        </EmptyState>
      )}
    </>
  )
}

BuildTable.propTypes = {
  builds: PropTypes.array.isRequired,
  fetching: PropTypes.bool.isRequired,
  onClearFilters: PropTypes.func.isRequired,
  tenant: PropTypes.object.isRequired,
  timezone: PropTypes.string.isRequired,
}

export default connect((state) => ({
  tenant: state.tenant,
  timezone: state.timezone,
}))(BuildTable)
