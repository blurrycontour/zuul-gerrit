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
import PropTypes from 'prop-types';
import { Badge, Checkbox, Form, FormGroup, FormControl } from 'patternfly-react'

import { Link } from 'react-router-dom'

import { fetchStatus } from '../api'
import './status.css'

import LineAngleImage from '../images/line-angle.png'
import LineTImage from '../images/line-t.png'

import { store } from '../reducers'

class ChangePanel extends React.Component {
  constructor () {
    super()
    this.state = {
      expanded: false
    }
    this.onClick = this.onClick.bind(this)
    this.clicked = false
  }
  onClick () {
    let expanded = this.state.expanded
    if (!this.clicked) {
      expanded = this.props.globalExpanded
    }
    this.clicked = true
    this.setState({ expanded: !expanded })
  }
  time (ms, words) {
    if (typeof (words) === 'undefined') {
      words = false
    }
    let seconds = (+ms) / 1000
    let minutes = Math.floor(seconds / 60)
    let hours = Math.floor(minutes / 60)
    seconds = Math.floor(seconds % 60)
    minutes = Math.floor(minutes % 60)
    let r = ''
    if (words) {
      if (hours) {
        r += hours
        r += ' hr '
      }
      r += minutes + ' min'
    } else {
      if (hours < 10) {
        r += '0'
      }
      r += hours + ':'
      if (minutes < 10) {
        r += '0'
      }
      r += minutes + ':'
      if (seconds < 10) {
        r += '0'
      }
      r += seconds
    }
    return r
  }
  enqueueTime (ms) {
    // Special format case for enqueue time to add style
    let hours = 60 * 60 * 1000
    let now = Date.now()
    let delta = now - ms
    let status = 'text-success'
    let text = this.time(delta, true)
    if (delta > (4 * hours)) {
      status = 'text-danger'
    } else if (delta > (2 * hours)) {
      status = 'text-warning'
    }
    return <span className={status}>{text}</span>
  }
  renderChangeLink (change) {
    let changeId = change.id || 'NA'
    let changeTitle = changeId
    let changeText = ''
    if (change.url !== null) {
      let githubId = changeId.match(/^([0-9]+),([0-9a-f]{40})$/)
      if (githubId) {
        changeTitle = githubId
        changeText = '#' + githubId[1]
      } else if (/^[0-9a-f]{40}$/.test(changeId)) {
        changeText = changeId.slice(0, 7)
      }
    } else if (changeId.length === 40) {
      changeText = changeId.slice(0, 7)
    }
    return (
      <small>
        <a href={change.url}>
          {changeText !== '' ? (
            <abbr title={changeTitle}>{changeText}</abbr>) : changeTitle}
        </a>
      </small>)
  }
  renderProgressBar (change) {
    let jobPercent = Math.floor(100 / change.jobs.length)
    return (
      <div className="progress zuul-change-total-result">
        {change.jobs.map((job, idx) => {
          let result = job.result ? job.result.toLowerCase() : null
          if (result === null) {
            result = job.url ? 'in progress' : 'queued'
          }
          if (result !== 'queued') {
            let className = ''
            switch (result) {
              case 'success':
                className = ' progress-bar-success'
                break
              case 'lost':
              case 'failure':
                className = ' progress-bar-danger'
                break
              case 'unstable':
                className = ' progress-bar-warning'
                break
              case 'in progress':
              case 'queued':
                break
              default:
                break
            }
            return <div className={'progress-bar' + className}
              key={idx}
              title={job.name}
              style={{width: jobPercent + '%'}}/>
          } else {
            return ''
          }
        })}
      </div>
    )
  }
  renderTimer (change) {
    return (
      <React.Fragment>
        <small title="Remaining Time" className="time">
          {this.time(change.remaining_time, true)}
        </small>
        <br />
        <small title="Elapsed Time" className="time">
          {this.enqueueTime(change.enqueue_time)}
        </small>
      </React.Fragment>
    )
  }

  renderJobProgressBar (elapsedTime, remainingTime) {
    let progressPercent = 100 * (elapsedTime / (elapsedTime +
                                                remainingTime))
    return (
      <div className="progress zuul-job-result">
        <div className="progress-bar"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          style={{'width': progressPercent + '%'}}
        />
      </div>
    )
  }
  renderJobStatusLabel (result) {
    let className
    switch (result) {
      case 'success':
        className = 'label-success'
        break
      case 'failure':
        className = 'label-danger'
        break
      case 'unstable':
        className = 'label-warning'
        break
      case 'skipped':
        className = 'label-info'
        break
      // 'in progress' 'queued' 'lost' 'aborted' ...
      default:
        className = 'label-default'
    }

    return (
      <span className={'zuul-job-result label ' + className}>{result}</span>
    )
  }

  renderJob (job) {
    let name = ''
    if (job.result !== null) {
      name = <a className="zuul-job-name" href={job.report_url}>{job.name}</a>
    } else if (job.url !== null) {
      let url = job.url
      let to
      if (job.url.match('stream.html')) {
        const buildUuid = job.url.split('?')[1].split('&')[0].split('=')[1]
        const state = store.getState()
        if (state.info.tenant) {
          to = '/stream/' + buildUuid
        } else {
          to = '/t/' + state.tenant + '/stream/' + buildUuid
        }
        name = <Link to={to}>{job.name}</Link>
      } else {
        name = <a className="zuul-job-name" href={url}>{job.name}</a>
      }
    } else {
      name = <span className="zuul-job-name">{job.name}</span>
    }
    let resultBar
    let result = job.result ? job.result.toLowerCase() : null
    if (result === null) {
      result = job.url ? 'in progress' : 'queued'
    }
    if (result === 'in progress') {
      resultBar = this.renderJobProgressBar(
        job.elapsed_time, job.remaining_time)
    } else {
      resultBar = this.renderJobStatusLabel(result)
    }

    return (
      <span>
        {name}
        {resultBar}
        {job.voting === false ? (
          <small className="zuul-non-voting-desc"> (non-voting)</small>) : ''}
        <div style={{clear: 'both'}} />
      </span>)
  }
  renderJobList (jobs) {
    return (
      <ul className="list-group zuul-patchset-body">
        {jobs.map((job, idx) => (
          <li key={idx} className="list-group-item zuul-change-job">
            {this.renderJob(job)}
          </li>
        ))}
      </ul>)
  }
  render () {
    const { expanded } = this.state
    const { change, globalExpanded } = this.props
    let expand = globalExpanded
    if (this.clicked) {
      expand = expanded
    }
    const header = (
      <div className="panel panel-default zuul-change" onClick={this.onClick}>
        <div className="panel-heading zuul-patchset-header">
          <div className="row">
            <div className="col-xs-8">
              <span className="change_project">{change.project}</span>
              <div className="row">
                <div className="col-xs-4">
                  {this.renderChangeLink(change)}
                </div>
                <div className="col-xs-8">
                  {this.renderProgressBar(change)}
                </div>
              </div>
            </div>
            {change.live === true ? (
              <div className="col-xs-4 text-right">
                {this.renderTimer(change)}
              </div>
            ) : ''}
          </div>
        </div>
        {expand ? this.renderJobList(change.jobs) : ''}
      </div>
    )
    return (
      <React.Fragment>
        {header}
      </React.Fragment>
    )
  }
}
ChangePanel.propTypes = {
  globalExpanded: PropTypes.bool.isRequired,
  change: PropTypes.object.isRequired
};

class Change extends React.Component {
  renderStatusIcon (change) {
    let iconGlyph = 'pficon pficon-ok'
    let iconTitle = 'Succeeding'
    if (change.active !== true) {
      iconGlyph = 'pficon pficon-pending'
      iconTitle = 'Waiting until closer to head of queue to' +
        ' start jobs'
    } else if (change.live !== true) {
      iconGlyph = 'fa fa-refresh'
      iconTitle = 'Dependent change required for testing'
    } else if (change.failing_reasons &&
               change.failing_reasons.length > 0) {
      let reason = change.failing_reasons.join(', ')
      iconTitle = 'Failing because ' + reason
      if (reason.match(/merge conflict/)) {
        iconGlyph = 'fa fa-ban'
      } else {
        iconGlyph = 'pficon pficon-error-circle-o'
      }
    }
    return (
      <span className={'zuul-build-status ' + iconGlyph}
        title={iconTitle} />
    )
  }
  renderLineImg (change, i) {
    let image = LineTImage
    if (change._tree_branches.indexOf(i) === change._tree_branches.length - 1) {
      // Angle line
      image = LineAngleImage
    }
    return <img alt="Line" src={image} style={{verticalAlign: 'baseline'}} />
  }
  render () {
    const { change, queue, expanded } = this.props
    let row = []
    let i
    for (i = 0; i < queue._tree_columns; i++) {
      let className = ''
      if (i < change._tree.length && change._tree[i] !== null) {
        className = ' zuul-change-row-line'
      }
      row.push(
        <td key={i} className={'zuul-change-row' + className}>
          {i === change._tree_index ? this.renderStatusIcon(change) : ''}
          {change._tree_branches.indexOf(i) !== -1 ? (
            this.renderLineImg(change, i)) : ''}
        </td>)
    }
    let changeWidth = 360 - 16 * queue._tree_columns
    row.push(
      <td key={i + 1}
        className="zuul-change-cell"
        style={{width: changeWidth + 'px'}}>
        <ChangePanel change={change} globalExpanded={expanded} />
      </td>
    )
    return (
      <table className="zuul-change-box" style={{boxSizing: 'content-box'}}>
        <tbody>
          <tr>{row}</tr>
        </tbody>
      </table>
    )
  }
}
Change.propTypes = {
  change: PropTypes.object.isRequired,
  queue: PropTypes.object.isRequired,
  expanded: PropTypes.bool.isRequired
};

class ChangeQueue extends React.Component {
  render () {
    const { queue, pipeline, expanded } = this.props
    let shortName = queue.name
    if (shortName.length > 32) {
      shortName = shortName.substr(0, 32) + '...'
    }
    let changesList = []
    queue.heads.forEach(changes => {
      changes.forEach((change, idx) => {
        changesList.push(
          <Change
            change={change}
            queue={queue}
            expanded={expanded}
            key={idx}
            />)
      })
    })
    return (
      <div className="change-queue" data-zuul-pipeline={pipeline}>
        <p>Queue: <abbr title={queue.name}>{shortName}</abbr></p>
        {changesList}
      </div>)
  }
}
ChangeQueue.propTypes = {
  pipeline: PropTypes.string.isRequired,
  queue: PropTypes.object.isRequired,
  expanded: PropTypes.bool.isRequired
};



class PipelineTree extends React.Component {
  createTree (pipeline) {
    let count = 0
    let pipelineMaxTreeColumns = 1
    pipeline.change_queues.forEach(changeQueue => {
      let tree = []
      let maxTreeColumns = 1
      let changes = []
      let lastTreeLength = 0
      changeQueue.heads.forEach(head => {
        head.forEach((change, changeIndex) => {
          changes[change.id] = change
          change._tree_position = changeIndex
        })
      })
      changeQueue.heads.forEach(head => {
        head.forEach(change => {
          if (change.live === true) {
            count += 1
          }
          let idx = tree.indexOf(change.id)
          if (idx > -1) {
            change._tree_index = idx
            // remove...
            tree[idx] = null
            while (tree[tree.length - 1] === null) {
              tree.pop()
            }
          } else {
            change._tree_index = 0
          }
          change._tree_branches = []
          change._tree = []
          if (typeof (change.items_behind) === 'undefined') {
            change.items_behind = []
          }
          change.items_behind.sort(function (a, b) {
            return (changes[b]._tree_position - changes[a]._tree_position)
          })
          change.items_behind.forEach(id => {
            tree.push(id)
            if (tree.length > lastTreeLength && lastTreeLength > 0) {
              change._tree_branches.push(tree.length - 1)
            }
          })
          if (tree.length > maxTreeColumns) {
            maxTreeColumns = tree.length
          }
          if (tree.length > pipelineMaxTreeColumns) {
            pipelineMaxTreeColumns = tree.length
          }
          change._tree = tree.slice(0) // make a copy
          lastTreeLength = tree.length
        })
      })
      changeQueue._tree_columns = maxTreeColumns
    })
    pipeline._tree_columns = pipelineMaxTreeColumns
    return count
  }

  filterQueue(queue, filter) {
    let found = false
    queue.heads.forEach(changes => {
      changes.forEach(change => {
        if (change.project.indexOf(filter) !== -1 ||
            change.id.indexOf(filter) !== -1) {
          found = true
          return
        }
      })
      if (found) {
        return
      }
    })
    return found;
  }

  render () {
    const { pipeline, filter, expanded } = this.props
    const count = this.createTree(pipeline)
    return (
      <div className="zuul-pipeline col-md-4">
        <div className="zuul-pipeline-header">
          <h3>{pipeline.name} <Badge>{count}</Badge></h3>
          {pipeline.description ? (
            <small>
              <p>{pipeline.description.split(/\r?\n\r?\n/)}</p>
            </small>) : ''}
        </div>
        {pipeline.change_queues.filter(item => item.heads.length > 0)
         .filter(item => (!filter || (
           pipeline.name.indexOf(filter) !== -1 ||
             this.filterQueue(item, filter)
         )))
          .map((changeQueue, idx) => (
            <ChangeQueue
              queue={changeQueue}
              expanded={expanded}
              pipeline={pipeline.name}
              key={idx}
              />
          ))}
      </div>
    )
  }
}
PipelineTree.propTypes = {
  expanded: PropTypes.bool.isRequired,
  pipeline: PropTypes.object.isRequired,
  filter: PropTypes.string.isRequired
};


class StatusPage extends React.Component {
  constructor () {
    super()

    this.state = {
      status: null,
      filter: null,
      expanded: false
    }
    this.handleKeyPress = this.handleKeyPress.bind(this)
    this.handleCheckBox = this.handleCheckBox.bind(this)
  }

  componentDidMount () {
    fetchStatus().then(response => {
      this.setState({status: response.data})
    })
  }

  handleKeyPress(e) {
    if (e.charCode===13) {
      this.setState({filter: e.target.value})
    }
  }
  handleCheckBox(e) {
    this.setState({expanded: e.target.checked})
  }

  render () {
    const { status, filter, expanded } = this.state
    if (!status) {
      return (<p>Loading...</p>)
    }
    const statusHeader = (
      <p>
        Queue lengths: <span>{status.trigger_event_queue ?
                              status.trigger_event_queue.length : '0'
          }</span> events,
        <span>{status.management_event_queue ?
               status.management_event_queue.length : '0'
          }</span> management events,
        <span>{status.result_event_queue ?
               status.result_event_queue.length : '0'
          }</span> results.
      </p>
    )
    const statusControl = (
      <Form inline>
        <FormGroup controlId="status">
          <FormControl
            type="text"
            placeholder="change number"
            onKeyPress={this.handleKeyPress} />
          &nbsp; Expand by default:&nbsp;
          <Checkbox
            onChange={this.handleCheckBox} />
        </FormGroup>
      </Form>
    )
    return (
      <React.Fragment>
        {statusHeader}
        {statusControl}
        <div className="row">
          {status.pipelines.map(item => (
            <PipelineTree
              pipeline={item}
              filter={filter}
              expanded={expanded}
              key={item.name}
              />
          ))}
        </div>
        <p>Zuul version: <span>{status.zuul_version}</span></p>
        {status.last_reconfigured ?
         <p>Last reconfigured: <span>{
           new Date(status.last_reconfigured).toString()
         }</span></p> : ''}
      </React.Fragment>)
  }
}

export default StatusPage
