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
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import Project from '../containers/project/Project'
import { fetchProjectIfNeeded } from '../actions/project'
import { Fetchable } from '../containers/Fetching'


class ProjectPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    isFetching: PropTypes.bool,
    project: PropTypes.object,
    tenant: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData = (force) => {
    this.props.dispatch(fetchProjectIfNeeded(
      this.props.tenant, this.props.match.params.projectName, force))
  }

  componentDidMount () {
    document.title = 'Zuul Project | ' + this.props.match.params.projectName
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  render () {
    return (
      <PageSection variant={PageSectionVariants.light}>
        <PageSection style={{paddingRight: '5px'}}>
          <Fetchable
            isFetching={this.props.isFetching}
            fetchCallback={this.updateData}
          />
          {this.props.project && <Project project={this.props.project} />}
        </PageSection>
      </PageSection>
    )
  }
}

function mapStateToProps(state) {
  return {
    tenant: state.tenant,
    isFetching: state.project.isFetching,
    project: state.project.project
  }
}

export default connect(mapStateToProps)(ProjectPage)
