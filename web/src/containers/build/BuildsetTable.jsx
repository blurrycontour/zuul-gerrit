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
  StreamIcon,
} from '@patternfly/react-icons'
import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
} from '@patternfly/react-table'

import { BuildResult, BuildResultWithIcon, IconProperty } from './Misc'
import { ExternalLink } from '../../Misc'

function BuildsetTable(props) {
  const { buildsets, fetching, onClearFilters, tenant } = props
  const columns = ['Project', 'Branch', 'Pipeline', 'Change', 'Result']

  function createBuildsetRow(buildset) {
    // This link will be defined on each cell of the current row as this is the
    // only way to define a valid HTML link on a table row. Although we could
    // simply define an onClick handler on the whole row and programatically
    // switch to the buildresult page, this wouldn't provide the same
    // look-and-feel as a plain HTML link.
    const buildsetResultLink = (
      <Link
        to={`${tenant.linkPrefix}/buildset/${buildset.uuid}`}
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
              {buildsetResultLink}
              <BuildResultWithIcon result={buildset.result}>
                {buildset.project}
              </BuildResultWithIcon>
            </>
          ),
        },
        {
          title: (
            <>
              {buildsetResultLink}
              <IconProperty icon={<CodeBranchIcon />} value={buildset.branch} />
            </>
          ),
        },
        {
          title: (
            <>
              {buildsetResultLink}
              <IconProperty icon={<StreamIcon />} value={buildset.pipeline} />
            </>
          ),
        },
        {
          title: (
            <>
              {buildsetResultLink}
              {buildset.change && (
                <IconProperty
                  icon={<CodeIcon />}
                  value={
                    <span style={{ zIndex: 1, position: 'relative' }}>
                      <ExternalLink target={buildset.ref_url}>
                        {buildset.change},{buildset.patchset}
                      </ExternalLink>
                    </span>
                  }
                />
              )}
            </>
          ),
        },
        {
          title: (
            <>
              {buildsetResultLink}
              <BuildResult result={buildset.result} />
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
  } else {
    rows = buildsets.map((buildset) => createBuildsetRow(buildset))
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

      {/* Show an empty state in case we don't have any buildsets but are also
          not fetching */}
      {!fetching && buildsets.length === 0 && (
        <EmptyState>
          <EmptyStateIcon icon={BuildIcon} />
          <Title headingLevel="h1">No buildsets found</Title>
          <EmptyStateBody>
            No buildsets match this filter criteria. Remove some filters or
            clear all to show results.
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

BuildsetTable.propTypes = {
  buildsets: PropTypes.array.isRequired,
  fetching: PropTypes.bool.isRequired,
  onClearFilters: PropTypes.func.isRequired,
  tenant: PropTypes.object.isRequired,
}

export default connect((state) => ({ tenant: state.tenant }))(BuildsetTable)
