// Copyright 2020 Red Hat, Inc
// Copyright 2022, 2024 Acme Gating, LLC
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
import { useSelector } from 'react-redux'
import PropTypes from 'prop-types'
import {
  EmptyState,
  EmptyStateBody,
  Spinner,
  Title,
} from '@patternfly/react-core'
import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
  expandable,
} from '@patternfly/react-table'
import { Link } from 'react-router-dom'
import ImageUploadTable from './ImageUploadTable'

function ImageBuildTable(props) {
  const { buildArtifacts, fetching } = props
  const [collapsedRows, setCollapsedRows] = React.useState([])
  const setRowCollapsed = (idx, isCollapsing = true) =>
        setCollapsedRows(prevCollapsed => {
          const otherCollapsedRows = prevCollapsed.filter(r => r !== idx)
          return isCollapsing ?
                [...otherCollapsedRows, idx] : otherCollapsedRows
        })
  const isRowCollapsed = idx => collapsedRows.includes(idx)
  const tenant = useSelector((state) => state.tenant)

  const columns = [
    {
      title: 'UUID',
      dataLabel: 'UUID',
      cellFormatters: [expandable],
    },
    {
      title: 'Timestamp',
      dataLabel: 'Timestamp',
    },
    {
      title: 'Validated',
      dataLabel: 'Validated',
    },
    {
      title: 'Build',
      dataLabel: 'Build',
    },
  ]

  function createImageBuildRow(rows, build) {
    return {
      id: rows.length,
      isOpen: !isRowCollapsed(rows.length),
      cells: [
        {
          title: build.uuid
        },
        {
          title: build.timestamp
        },
        {
          title: build.validated.toString()
        },
        {
          // TODO: This may not be a valid link if it's outside this tenant;
          // consider hiding it in that case.
          title: <Link to={`${tenant.linkPrefix}/build/${build.build_uuid}`}>
                   {build.build_uuid}
                 </Link>
        },
      ]
    }
  }
  function createImageUploadRow(rows, parent, build) {
    return {
      id: rows.length,
      parent: parent.id,
      cells: [
        {
          title: <ImageUploadTable uploads={build.uploads}
                                   fetching={fetching}/>
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

  const haveBuildArtifacts = buildArtifacts && buildArtifacts.length > 0

  let rows = []
  if (fetching) {
    rows = createFetchingRow()
    columns[0].dataLabel = ''
  } else {
    if (haveBuildArtifacts) {
      rows = []
      buildArtifacts.forEach(build => {
        let buildRow = createImageBuildRow(rows, build)
        rows.push(buildRow)
        rows.push(createImageUploadRow(rows, buildRow, build))
      })
    }
  }

  return (
    <>
      <Title headingLevel="h3">
        Image Build Artifacts
      </Title>
      <Table
        aria-label="Image Build Table"
        variant={TableVariant.compact}
        cells={columns}
        rows={rows}
        onCollapse={(_event, rowIndex, isOpen) => {
          setRowCollapsed(rowIndex, !isOpen)
        }}
        className="zuul-table"
      >
        <TableHeader />
        <TableBody />
      </Table>

      {/* Show an empty state in case we don't have any build artifacts but are also not
          fetching */}
      {!fetching && !haveBuildArtifacts && (
        <EmptyState>
          <Title headingLevel="h1">No build artifacts found</Title>
          <EmptyStateBody>
            Nothing to display.
          </EmptyStateBody>
        </EmptyState>
      )}
    </>
  )
}

ImageBuildTable.propTypes = {
  buildArtifacts: PropTypes.array,
  fetching: PropTypes.bool.isRequired,
}

export default ImageBuildTable
