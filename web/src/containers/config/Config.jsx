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
import {
  Nav,
  NavItem,
  TabContainer,
  TabPane,
  TabContent,
  Icon,
  ListView,
} from 'patternfly-react'


class ConfigObjects extends React.Component {
  static propTypes = {
    link: PropTypes.string,
    name: PropTypes.string,
    objects: PropTypes.array,
  }

  render () {
    const { link, objects } = this.props
    return (
      <ListView>
        {Object.entries(objects)
         .sort((a, b) => a[1].length < b[1].length)
         .map(([name, users]) => (
          users.length === 0 ?
            <ListView.Item
              key={name}
              heading={name}
              additionalInfo={[
                <ListView.InfoItem key='ko' title='Unused'>
                  <Icon type='pf' name='warning-triangle-o' />
                  <strong>Unused</strong>
                </ListView.InfoItem>
              ]}
              />
          :
            <ListView.Item
              key={name}
              heading={name}
              additionalInfo={[
                <ListView.InfoItem key='ok' title='Users'>
                  <Icon type='pf' name='info' />
                  <strong>{users.length}</strong>
                </ListView.InfoItem>
              ]}
              >
              <ul key={name}>
                {users.map((user, idx) => (
                  <li key={idx}>
                    {link ? <Link to={link + user}>{user}</Link> : user}
                  </li>
                ))}
              </ul>
            </ListView.Item>
        ))}
      </ListView>
    )
  }
}


class Config extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    config: PropTypes.object,
  }

  state = {
    catName: 'pipelines'
  }

  render () {
    const { config } = this.props
    const { catName } = this.state
    const configs = {}
    const configCats = [
      ['pipelines', 'project'],
      ['projects', 'job'],
      ['jobs', 'project'],
      ['labels', 'job'],
      ['nodesets', 'job'],
      ['semaphores', 'job'],
      ['secrets', 'project'],
    ]
    for (let cat of configCats) {
      configs[cat[0]] = {objects: [], link: '/' + cat[1] + '/'}
    }
    for (let pipeline of config.layout.pipelines) {
      configs.pipelines.objects[pipeline.name] = []
    }
    for (let secret of config.layout.secrets) {
      configs.secrets.objects[secret.name] = []
    }
    for (let semaphore of config.layout.semaphores) {
      configs.semaphores.objects[semaphore.name] = []
    }
    for (let nodeset of config.layout.nodesets) {
      configs.nodesets.objects[nodeset.name] = []
    }
    const ensureObject = function (cat, name, obj) {
      if (!configs[cat].objects[name]) {
        configs[cat].objects[name] = []
      }
      if (configs[cat].objects[name].indexOf(obj) === -1) {
        configs[cat].objects[name].push(obj)
      }
    }
    for (let job of config.layout.jobs) {
      const jobName = job[0].name
      configs.jobs.objects[jobName] = []
      // Add job to secrets, nodeset, labels and semaphore user
      for (let jobVariant of job) {
        if (jobVariant.semaphore) {
          ensureObject('semaphores', jobVariant.semaphore, jobName)
        }
        if (jobVariant.nodeset) {
          if (jobVariant.nodeset.name) {
            ensureObject('nodesets', jobVariant.nodeset.name, jobName)
          }
          for (let node of jobVariant.nodeset.nodes) {
            ensureObject('labels', node.label, jobName)
          }
        }
        for (let pbCat of ['pre_run', 'run', 'post_run']) {
          for (let playbook of jobVariant[pbCat]) {
            for (let secret of playbook.secrets) {
              ensureObject('secrets', secret.name, jobName)
            }
          }
        }
      }
    }
    for (let project of config.projects) {
      configs.projects.objects[project.name] = []
      // Add project to jobs and pipelines user
      for (let projectVariant of project.configs) {
        for (let pipeline of projectVariant.pipelines) {
          ensureObject('pipelines', pipeline.name, project.name)
          for (let job of pipeline.jobs) {
            ensureObject('jobs', job[0].name, project.name)
            ensureObject('projects', project.name, job[0].name)
          }
        }
      }
    }
    return (
      <TabContainer id='zuul-config'>
          <div>
            <Nav bsClass='nav nav-tabs nav-tabs-pf'>
              {configCats.map((cat, idx) => (
                <NavItem
                  key={idx}
                  onClick={() => this.setState({catName: cat[0]})}>
                  <div>
                    {cat[0] === catName ? <strong>{cat[0]}</strong> : cat[0]} (
                    {Object.keys(configs[cat[0]].objects).length})
                  </div>
                </NavItem>
              ))}
            </Nav>
            <TabContent>
              <TabPane>
                <ConfigObjects
                  name={catName}
                  objects={configs[catName].objects}
                  link={this.props.tenant.linkPrefix + configs[catName].link}
                />
              </TabPane>
            </TabContent>
          </div>
      </TabContainer>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
}))(Config)
