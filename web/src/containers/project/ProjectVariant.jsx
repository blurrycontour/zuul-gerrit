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
import PropTypes from 'prop-types'
import { withRouter } from 'react-router-dom'
import { connect } from 'react-redux'
import { Link } from 'react-router-dom'
import { Button } from 'patternfly-react'

import * as API from '../../api'


class ProjectVariant extends React.Component {
  static propTypes = {
    projectName: PropTypes.string,
    tenant: PropTypes.object,
    pipelines: PropTypes.array,
    variant: PropTypes.object.isRequired,
    history: PropTypes.object.isRequired,
  }

  triggerJob = (jobName) => {
    const { projectName, tenant } = this.props
    API.triggerJobs(tenant.apiPrefix, projectName, [jobName])
      .then(() => this.props.history.push(tenant.linkPrefix + '/status'))
      .catch(error => console.error('oops', error))
  }

  render () {
    const { pipelines, tenant, variant } = this.props
    const rows = []

    rows.push({label: 'Merge mode', value: variant.merge_mode})

    if (variant.templates.length > 0) {
      const templateList = (
        <ul className='list-group'>
          {variant.templates.map((item, idx) => (
            <li className='list-group-item' key={idx}>{item}</li>))}
        </ul>
      )
      rows.push({label: 'Templates', value: templateList})
    }

    const pipelineWebTrigger = []
    pipelines.forEach(pipeline => {
      pipeline.triggers.forEach(trigger => {
        if (trigger.name === 'web') {
          pipelineWebTrigger.push(pipeline.name)
        }
      })
    })

    variant.pipelines.forEach(pipeline => {
      // TODO: either adds job link anchor to load the right variant
      // and/or show the job variant config in a modal?
      const jobList = (
        <React.Fragment>
          {pipeline.queue_name && (
            <p><strong>Queue: </strong> {pipeline.queue_name} </p>)}
          <ul className='list-group'>
            {pipeline.jobs.map((item, idx) => (
              <li className='list-group-item' key={idx}>
                {pipelineWebTrigger.indexOf(pipeline.name) !== -1 && (
                  <Button
                    onClick={() => this.triggerJob(item[0].name)}
                    bsStyle='primary'
                    style={{marginRight: '5px'}}
                    title='Trigger this job'>
                    Build
                  </Button>
                )}
                <Link to={tenant.linkPrefix + '/job/' + item[0].name}>
                  {item[0].name}
                </Link>
              </li>
            ))}
          </ul>
        </React.Fragment>
      )
      rows.push({label: pipeline.name + ' jobs', value: jobList})
    })

    return (
      <div>
        <table className='table table-striped table-bordered'>
          <tbody>
            {rows.map(item => (
              <tr key={item.label}>
                <td style={{width: '10%'}}>{item.label}</td>
                <td>{item.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
}

export default withRouter(connect(state => ({
  tenant: state.tenant
}))(ProjectVariant))
