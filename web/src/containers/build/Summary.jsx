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
import { connect } from 'react-redux'
import { Link } from 'react-router-dom'
import { Translate } from 'react-redux-i18n'

import ArtifactList from './Artifact'
import BuildOutput from './BuildOutput'

import * as moment from 'moment'
import 'moment-duration-format'


class Summary extends React.Component {
  static propTypes = {
    build: PropTypes.object,
    tenant: PropTypes.object,
    timezone: PropTypes.string,
  }

  render () {
    const { build } = this.props
    const rows = []
    const myColumns = [
      'job_name', 'result', 'buildset', 'voting',
      'pipeline', 'start_time', 'end_time', 'duration',
      'project', 'branch', 'change', 'patchset', 'oldrev', 'newrev',
      'ref', 'new_rev', 'ref_url', 'log_url', 'event_id']

    if (!build.buildset) {
      // Safely handle missing buildset information
      myColumns.splice(myColumns.indexOf('buildset'), 1)
    }

    myColumns.forEach(column => {
      let label = (<Translate value={column} />)
      if (column === 'job_name') {
        label = (<Translate value='job name' />)
      }
      if (column === 'start_time') {
        label = (<Translate value='start time' />)
      }
      if (column === 'end_time') {
        label = (<Translate value='end time' />)
      }
      if (column === 'oldrev') {
        label = (<Translate value='old revision' />)
      }
      if (column === 'newrev' || column === 'new_rev' ) {
        label = (<Translate value='new revision' />)
      }
      if (column === 'ref_url') {
        label = (<Translate value='ref URL' />)
      }
      if (column === 'log_url') {
        label = (<Translate value='log URL' />)
      }
      if (column === 'event_id') {
        label = (<Translate value='event ID' />)
      }
      let value = build[column]
      if (column === 'job_name') {
        value = (
          <React.Fragment>
          <Link to={this.props.tenant.linkPrefix + '/job/' + value}>
            {value}
          </Link>
          <span> &mdash; </span>
          <Link to={this.props.tenant.linkPrefix + '/builds?job_name=' + value + '&project=' + build.project}
                title="See previous runs of this job inside current project.">
            <Translate value='build history' />
          </Link>
          </React.Fragment>
        )
      }
      if (column === 'buildset') {
        value = (
          <Link to={this.props.tenant.linkPrefix + '/buildset/' + value.uuid}>
            {value.uuid}
          </Link>
        )
      }
      if (column === 'voting') {
        if (value) {
          value = <Translate value='true' />
        } else {
          value = <Translate value='false' />
        }
      }
      if (column === 'start_time' || column === 'end_time') {
        value = moment.utc(value).tz(this.props.timezone).format('YYYY-MM-DD HH:mm:ss')
      }
      if (column === 'duration') {
          value = moment.duration(value, 'seconds')
            .format('h [hr] m [min] s [sec]')
      }
      if (value && (column === 'log_url' || column === 'ref_url')) {
        value = <a href={value}>{value}</a>
      }
      if (column === 'log_url') {
        if (build.manifest && build.manifest.index_links) {
          value = <a href={value + 'index.html'}>{value}</a>
        } else {
          value = <a href={value}>{value}</a>
        }
      }
      if (column === 'ref_url') {
        value = <a href={value}>{value}</a>
      }
      if (value) {
        rows.push({key: label, value: value})
      }
    })
    return (
      <React.Fragment>
        <br/>
        <table className="table table-striped table-bordered">
          <tbody>
            {rows.map(item => (
              <tr key={item.key}>
                <td>{item.key}</td>
                <td>{item.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3><Translate value='Artifacts' /></h3>
        <ArtifactList build={build}/>
        <h3><Translate value='Results' /></h3>
        {build.hosts && <BuildOutput output={build.hosts}/>}
      </React.Fragment>
    )
  }
}


export default connect(state => ({tenant: state.tenant, timezone: state.timezone}))(Summary)
