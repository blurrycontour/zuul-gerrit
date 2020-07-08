// Copyright 2019 Red Hat, Inc
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
import { TreeView } from 'patternfly-react'
import {
  BugIcon,
  ClipboardListIcon,
  DesktopIcon,
  DockerIcon,
  DownloadIcon,
  FileArchiveIcon,
  FilePdfIcon,
  JsSquareIcon,
  PythonIcon,
} from '@patternfly/react-icons'

import { IconProperty } from './Misc'
import { ExternalLink } from '../../Misc'

const ARTIFACT_ICONS = {
  container_image: DockerIcon,
  docs_archive: FileArchiveIcon,
  docs_pdf: FilePdfIcon,
  docs_site: DesktopIcon,
  javascript_content: JsSquareIcon,
  python_wheel: PythonIcon,
  python_sdist: PythonIcon,
  site: DesktopIcon,
  unit_test_report: BugIcon,
  zuul_manifest: ClipboardListIcon,
}

const DEFAULT_ARTIFACT_ICON = DownloadIcon

class Artifact extends React.Component {
  static propTypes = {
    artifact: PropTypes.object.isRequired
  }

  render() {
    const { artifact } = this.props
    return (
      <table className="table table-striped table-bordered" style={{width:'50%'}}>
        <tbody>
          {Object.keys(artifact.metadata).map(key => (
            <tr key={key}>
              <td>{key}</td>
              <td style={{width:'100%'}}>{artifact.metadata[key]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
}

function ArtifactList(props) {
  const { artifacts } = props

  const nodes = artifacts.map((artifact, index) => {
    let Icon = ARTIFACT_ICONS[artifact.metadata.type]
    if (!Icon) {
      Icon = DEFAULT_ARTIFACT_ICON
    }

    const node = {
      text: (
        <IconProperty
          icon={<Icon />}
          value={
            <ExternalLink target={artifact.url}>{artifact.name}</ExternalLink>
          }
        />
      ),
      icon: null,
    }
    if (artifact.metadata) {
      node['nodes'] = [
        { text: <Artifact key={index} artifact={artifact} />, icon: '' },
      ]
    }
    return node
  })

  return (
    <>
      <br />
      <div className="tree-view-container">
        <TreeView nodes={nodes} />
      </div>
    </>
  )
}

ArtifactList.propTypes = {
  artifacts: PropTypes.array.isRequired,
}

export default ArtifactList
