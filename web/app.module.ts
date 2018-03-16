// Entrypoint for Zuul dashboard pages
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

import './styles/zuul.css'

import { NgModule } from '@angular/core'
import { BrowserModule } from '@angular/platform-browser'
import { HttpClientModule } from '@angular/common/http'
import { FormsModule }   from '@angular/forms'

import { AppRoutingModule } from './app-routing.module'
import { AppComponent } from './app.component'

import BuildsComponent from './builds/builds.component'
import NavigationComponent from './navigation/navigation.component'
import ProjectComponent from './project/project.component'
import ProjectsComponent from './projects/projects.component'
import StatusComponent from './status/status.component'
import StreamComponent from './stream/stream.component'


@NgModule({
  imports: [
    BrowserModule,
    HttpClientModule,
    FormsModule,
    AppRoutingModule,
  ],
  declarations: [
    AppComponent,
    BuildsComponent,
    NavigationComponent,
    ProjectComponent,
    ProjectsComponent,
    StatusComponent,
    StreamComponent
  ],
  entryComponents: [
    BuildsComponent,
    NavigationComponent,
    ProjectComponent,
    ProjectsComponent,
    StatusComponent,
    StreamComponent
  ],
  bootstrap: [
    AppComponent
  ]
})
export class AppModule { }
