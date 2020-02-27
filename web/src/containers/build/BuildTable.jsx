// Copyright 2020 BMW Group
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
import { Icon } from 'patternfly-react'
import { Link } from 'react-router-dom'
import * as moment from 'moment'

// TODO (felix): If we need this functionality also in other places and not
// only for builds, we might want to make this class more generic.
// Found on https://gist.github.com/markerikson/bd9f03e0808558c5951e02f1aa98c563
// and adapted it to our needs.
class ExpandableBuildsTable extends React.Component {
  constructor() {
    super();

    this.state = {
      expandedRows: []
    };
  }

  handleRowClick(rowId) {
    const currentExpandedRows = this.state.expandedRows;
    const isRowCurrentlyExpanded = currentExpandedRows.includes(rowId);

    const newExpandedRows = (
      isRowCurrentlyExpanded ? currentExpandedRows.filter(
        id => id !== rowId
      ) : currentExpandedRows.concat(rowId)
    )

    this.setState({ expandedRows: newExpandedRows });
  }

  renderItem(build, tenant) {
    const clickCallback = () => this.handleRowClick(build.uuid);
    const hasRetries = build.retries.length > 0 ? true : false;
    const itemRows = [
      <tr {...(hasRetries ? { onClick: clickCallback } : {})} key={"row-data-" + build.uuid} className={build.result === 'SUCCESS' ? 'success' : 'warning'}>
        <td>{hasRetries ? <Icon type="fa" name="plus" /> : ''} {build.job_name}</td>
        <td><Link to={tenant.linkPrefix + '/build' + build.uuid}>{build.result}</Link></td>
        <td>{build.voting ? 'true' : 'false'}</td>
        <td>{moment.duration(build.duration, 'seconds').humanize()}</td>
      </tr>
    ];

    if (this.state.expandedRows.includes(build.uuid)) {
      build.retries.forEach(retry => {
        itemRows.push(
          <tr key={"row-expanded-" + retry.uuid} className={retry.result === 'SUCCESS' ? 'success' : 'warning'}>
            <td>{retry.job_name}</td>
            <td><Link to={tenant.linkPrefix + '/build' + retry.uuid}>{retry.result}</Link></td>
            <td>{retry.voting ? 'true' : 'false'}</td>
            <td>{moment.duration(retry.duration, 'seconds').humanize()}</td>
          </tr>
        );
      })
    }

    return itemRows;
  }

  render() {
    let allItemRows = [];

    this.props.data.forEach(item => {
      const perItemRows = this.renderItem(item, this.props.tenant);
      allItemRows = allItemRows.concat(perItemRows);
    });

    const headerCols = []
    this.props.cols.forEach(col => {
      console.log(col);
      headerCols.push(<td>{col}</td>);
    });
    console.log(this.props.cols);

    return (
      <table className="table table-striped table-bordered">
        <thead>
          <tr>
            {headerCols}
          </tr>
        </thead>
        <tbody>
          {allItemRows}
        </tbody>
      </table>
    );
  }
}

export default connect(state => ({tenant: state.tenant}))(ExpandableBuildsTable)
