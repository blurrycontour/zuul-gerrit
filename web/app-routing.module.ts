// Routing information for Zuul dashboard pages
//
// @licstart  The following is the entire license notice for the
// JavaScript code in this page.
//
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
//
// @licend  The above is the entire license notice
// for the JavaScript code in this page.

import { NgModule } from '@angular/core'
import { RouterModule, Routes } from '@angular/router'

import BuildsComponent from './builds/builds.component'
import JobComponent from './job/job.component'
import JobsComponent from './jobs/jobs.component'
import ProjectComponent from './project/project.component'
import ProjectsComponent from './projects/projects.component'
import StatusComponent from './status/status.component'
import StreamComponent from './stream/stream.component'
import TenantsComponent from './tenants/tenants.component'

// Have all routes go to builds.html for now
const appRoutes: Routes = [
  {
    path: ':tenant/builds.html',
    component: BuildsComponent
  },
  {
    path: 'builds.html',
    component: BuildsComponent
  },
  {
    path: ':tenant/status.html',
    component: StatusComponent
  },
  {
    path: 'status.html',
    component: StatusComponent
  },
  {
    path: ':tenant/job.html',
    component: JobComponent
  },
  {
    path: 'job.html',
    component: JobComponent
  },
  {
    path: ':tenant/jobs.html',
    component: JobsComponent
  },
  {
    path: 'jobs.html',
    component: JobsComponent
  },
  {
    path: ':tenant/project.html',
    component: ProjectComponent
  },
  {
    path: 'project.html',
    component: ProjectComponent
  },
  {
    path: ':tenant/projects.html',
    component: ProjectsComponent
  },
  {
    path: 'projects.html',
    component: ProjectsComponent
  },
  {
    path: 'stream.html',
    component: StreamComponent
  },
  {
    path: ':tenant/stream.html',
    component: StreamComponent
  },
  {
    path: 'tenants.html',
    component: TenantsComponent
  },
  {
    path: '**',
    component: StatusComponent
  },
]

@NgModule({
  imports: [RouterModule.forRoot(appRoutes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
