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
} from '@patternfly/react-table'

function ImageUploadTable(props) {
  const { uploads, fetching } = props

  const columns = [
    {
      title: 'UUID',
      dataLabel: 'UUID',
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
      title: 'Endpoint',
      dataLabel: 'Endpoint',
    },
    {
      title: 'External ID',
      dataLabel: 'External ID',
    },
  ]

  function createImageUploadRow(upload) {
    return {
      cells: [
        {
          title: upload.uuid
        },
        {
          title: upload.timestamp
        },
        {
          title: upload.validated.toString()
        },
        {
          title: upload.endpoint_name
        },
        {
          title: upload.external_id
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

  const haveUploads = uploads && uploads.length > 0

  let rows = []
  if (fetching) {
    rows = createFetchingRow()
    columns[0].dataLabel = ''
  } else {
    if (haveUploads) {
      rows = uploads.map((upload) => createImageUploadRow(upload))
    }
  }

  return (
    <>
      <Title headingLevel="h3">
        Image Uploads
      </Title>
      <Table
        aria-label="Image Upload Table"
        variant={TableVariant.compact}
        cells={columns}
        rows={rows}
        className="zuul-table"
      >
        <TableHeader />
        <TableBody />
      </Table>

      {/* Show an empty state in case we don't have any build artifacts but are also not
          fetching */}
      {!fetching && !haveUploads && (
        <EmptyState>
          <Title headingLevel="h1">No image uploads found</Title>
          <EmptyStateBody>
            Nothing to display.
          </EmptyStateBody>
        </EmptyState>
      )}
    </>
  )
}

ImageUploadTable.propTypes = {
  uploads: PropTypes.array,
  fetching: PropTypes.bool.isRequired,
}

export default ImageUploadTable
