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

import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  BuildIcon,
  CubeIcon,
  CubesIcon,
  DesktopIcon,
  FolderIcon,
  HomeIcon,
  RepositoryIcon,
  TrendUpIcon
} from '@patternfly/react-icons'
import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
} from '@patternfly/react-table'
import { useDispatch } from 'react-redux'

import { PageSection, PageSectionVariants } from '@patternfly/react-core'
import { IconProperty } from '../containers/build/Misc'
import { fetchTenants } from '../api.js'

const TenantsPage = () => {
  const [data, setData] = useState([])
  const dispatch = useDispatch()
  // TODO: use a custom hook to take care of catching and dispatching network errors
  useEffect(() => {
    document.title = 'Zuul Tenants'
    fetchTenants()
      .then(response => setData(response.data))
      .catch(error => dispatch({type: 'TENANTS_FETCH_FAIL', error}))
  }, [dispatch])

  const tenants = data.map((tenant) => {
    return {
      cells: [
        {title: (<b>{tenant.name}</b>)},
        {title: (<Link to={'/t/' + tenant.name + '/status'}>Status</Link>)},
        {title: (<Link to={'/t/' + tenant.name + '/projects'}>Projects</Link>)},
        {title: (<Link to={'/t/' + tenant.name + '/jobs'}>Jobs</Link>)},
        {title: (<Link to={'/t/' + tenant.name + '/builds'}>Builds</Link>)},
        {title: (<Link to={'/t/' + tenant.name + '/buildsets'}>Buildsets</Link>)},
        tenant.projects,
        tenant.queue
      ]}})
  const columns = [
    {
      title: <IconProperty icon={<HomeIcon />} value="Name"/>,
      dataLabel: 'Name',
    },
    {
      title: <IconProperty icon={<DesktopIcon />} value="Status"/>,
      dataLabel: 'Status',
    },
    {
      title: <IconProperty icon={<CubeIcon />} value="Projects"/>,
      dataLabel: 'Projects',
    },
    {
      title: <IconProperty icon={<BuildIcon />} value="Jobs"/>,
      dataLabel: 'Jobs',
    },
    {
      title: <IconProperty icon={<FolderIcon />} value="Builds"/>,
      dataLabel: 'Builds',
    },
    {
      title: <IconProperty icon={<RepositoryIcon />} value="Buildsets"/>,
      dataLabel: 'Buildsets',
    },
    {
      title: <IconProperty icon={<CubesIcon />} value="Project count"/>,
      dataLabel: 'Project count',
    },
    {
      title: <IconProperty icon={<TrendUpIcon />} value="Queue"/>,
      dataLabel: 'Queue',
    }
  ]

  return (
    <PageSection variant={PageSectionVariants.light}>
      <Table
        aria-label="Tenant Table"
        variant={TableVariant.compact}
        cells={columns}
        rows={tenants}
        className="zuul-tenant-table"
      >
        <TableHeader />
        <TableBody />
      </Table>
    </PageSection>
  )
}

export default TenantsPage
