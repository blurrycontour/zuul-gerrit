// Copyright 2022 Red Hat, Inc
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
  Button,
  Divider,
  Flex,
  FlexItem,
  Label,
  LabelGroup,
  PageSection,
  Popover,
  Text,
  TextContent,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  TreeView,
  SearchInput
} from '@patternfly/react-core'

import {
  CodeBranchIcon
} from '@patternfly/react-icons'

class JobsList extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    jobs: PropTypes.array,
  }

  state = {
    allItems: [],
    filteredItems: [],
    isFiltered: false,
    searchValue: '',
  }

  constructor(props) {
    super(props)

    const { jobs } = props

    /*
     * We are getting in job elements that look like
     * job = {
     *  name : 'job name'
     *  description : 'description'
     *  variants: [
     *    branches: ['master'], <- optional
     *    parent: 'string'
     *  ]
     *
     * The first thing we do is put this in a map indexed by the job
     * name and add some fields so we can manage relationships.
     *
     */
    let jobList = {}
    jobs.forEach(job => {
      jobList[job.name] = {
        ...job,
        'unmergedChildren': [],
        'children': []
      }
    })

    /*
     * Currently jobs point to their parents, but parents don't have a
     * list of children.  Every job has an array "variants" which
     * lists the branches it exists on and the parent job for that
     * branch.
     *
     * So we go through every job, find it's parent in jobList and
     * append it to the umergedChildren list, along with it's variant
     * array index.
     *
     * It can be tricky; jobs can change parents.  So consider; job
     * foo is like
     *
     *  jobList.foo = { name: 'foo',
     *                  description: 'something',
     *                  variants: [{
     *                    branches: ['master']
     *                    parent: 'foo-parent'
     *                  }, {
     *                    branches: ['v2']
     *                    parent: 'foo-parent'
     *                  }, {
     *                    branches: ['old-branch']
     *                    parent: 'old-parent'
     *                  }]
     *                }
     *
     * In this case, "foo-parent" will have a child list
     *
     *  [ { job: jobList['foo'], v: 0 }, { job: jobList['foo'], v: 1 } ]
     *
     * and "old-parent" will have a child list
     *
     *  [ { job: jobList['foo'], v: 1 } ]
     *
     */
    for (const name of Object.keys(jobList)) {
      const job = jobList[name]
      if (job.variants) {
        job.variants.forEach( (variant, idx) => {
          if (!jobList[variant.parent]) {
            /* Jobs without a parent are broken; Zuul can be in this state
             * showing config errors.  Ignore them here */
            console.log(name + ' can not find parent ' + variant.parent)
          } else {
            jobList[variant.parent].unmergedChildren.push(
              {'job': job, 'v': idx})
          }
        })
      } else {
        console.log('Job ' + name + ' does not have any variants and hence no parent')
      }
    }

    /* Now we take the unmergedChildren list, and merge jobs to group
     * their branches for display into the children array.
     * Following our  example above; we'll have
     *
     * jobList['foo-parent'].children =
     *   [{ job: jobList[foo'], branches : ['master', /v2'] }]
     *
     * i.e. each parent has a list of children jobs and a related list of
     * branches it runs on.
     */
    for (const name of Object.keys(jobList)) {
      this.mergeVariants(jobList[name])
    }

    /* Anything without a variant is our root elements */
    let treeList = []
    for (const name of Object.keys(jobList)) {
      if (!jobList[name].variants) {
        treeList.push({'job': jobList[name], 'branches': []})
      }
    }

    /*
     * Now build it into a list suitable for the TreeView element to display.
     */
    let items = []
    treeList.forEach( x => items.push(this.makeTreeView(x, {})))

    this.state = {
      allItems: items,
      filteredItems: items,
      isFiltered: false
    }
  }

  /*
   * Each child in a job's umergedChildren is a map
   *
   *  child.job -> pointer to the job defintion
   *  child.v   -> the index to child.job.variants[]
   *               for this particular child.
   *
   * Thus for each child in the umergedChildren array, looking at
   * child.job.variants[child.v].branches would give you all the
   * branches this child matches against.
   *
   * This function goes through all the children, and merges all the
   * variants of a job.  The resulting "children" array has elements
   *
   *  child.job -> pointer to the job
   *  child.branches -> string array of branches
   *
   * This is then easy to display.
   *
   */
  mergeVariants = job => {
    let mergedChildren = []
    job.unmergedChildren.forEach(child => {
      /* the branches this variant is for */
      let branches = child.job.variants[child.v].branches ?
          child.job.variants[child.v].branches : []
      //console.log("Processing " + child.job.name + " on " + branches.join(","))
      /* if it's not in merged children, it should be */
      if (!mergedChildren[child.job.name]) {
        mergedChildren[child.job.name] = {
          'job': child.job,
          'branches': branches
        }
      } else {
        /* otherwise, the variant is telling us this job runs on
         * another branch.  record it */
        mergedChildren[child.job.name].branches = [
          ...mergedChildren[child.job.name].branches,
          ...branches
        ]
      }
    })

    for (const name of Object.keys(mergedChildren)) {
      job.children.push(
        {
          'job': mergedChildren[name].job,
          'branches': mergedChildren[name].branches
        })
    }
  }

  /*
   * This is a recursive function to turn our job elements into a TreeView.
   * Each element has
   *  {
   *    job : job object we are passed in
   *    branches : list of string branches this job is for
   *    children : list of children job objects
   *  }
   *
   * Walk this recursively to build up the TreeView layout which is
   *  [{ name: Display name
   *     id: id
   *     children: [{ ... }]
   *   }, ... ]
   *
   * One caveat; consider
   *
   *  a has children [b, c] for branches foo, bar
   *  b has children [a, c] for branches moo, goo
   *
   * is a valid situation if a and b have swapped parents on various
   * branches (if this is a good idea for your sanity is another
   * question...).  We mark children as visited to avoid looping in
   * this case.
   */
  makeTreeView = (element, visited) => {
    let branches = element.branches
    let job = element.job
    let children = []
    if (job.children.length > 0) {
      job.children.forEach(child => {
        if (!(child.job.name in visited)) {
          visited[child.job.name] = true
          children.push(this.makeTreeView(child, visited))
        }
      })
    }

    let branchStatus = null
    if (branches.length > 0) {
      branchStatus = <FlexItem>
                       <Popover
                         headerContent={<div>Branches for {job.name}</div>}
                         bodyContent={
                           <LabelGroup numLabels={20} isCompact isVertical>
                             {
                               branches.map((branch, idx) =>
                                 <Label key={idx}
                                        icon={<CodeBranchIcon />}
                                        variant="outline" color="grey">
                                   {branch}
                                 </Label>)
                             }
                           </LabelGroup>
                         }>
                         <Label
                           icon={<CodeBranchIcon/>}
                           style={{ cursor: 'pointer'}} >
                           {branches.length}
                         </Label>
                       </Popover>
                     </FlexItem>
    }

    let tags = null
    if (!(job.tags === undefined)) {
      tags = <FlexItem>
               <LabelGroup>
                 {job.tags.map((tag, idx) =>
                   <Label key={idx} color="blue">{tag}</Label>)}
               </LabelGroup>
             </FlexItem>
    }

    return {
      'name': <Flex>
                <FlexItem>
                  <Link to={this.props.tenant.linkPrefix + encodeURIComponent('/job/' + job.name)}>{job.name}</Link>
                </FlexItem>
                { job.description ?
                  <FlexItem>
                    <TextContent>
                      <Text  style={{ color: 'var(--pf-global--palette--black-500)' }}>
                        {job.description}
                      </Text>
                    </TextContent>
                  </FlexItem> : null }
                { branchStatus }
                { tags }
              </Flex>,
      'id': job.name,
      children: children.length > 0 ? children : null
    }
  }

  onSearch = value => {
    const { allItems } = this.state
    if (value === '') {
      this.setState({ filteredItems: allItems, isFiltered: false, searchValue: value })
    }  else if (value.length < 5) {
      /* This is a bit of a hack to not run the search until we have
       * sufficient characters to narrow the list a bit.  Expanding
       * thousands of jobs in huge tenants makes this terrible when
       * you're typing a single character.
       *
       * Enhancement ideas:
       *  - only need to do this for huge tenants?
       *  - some sort of timestamp/callback approach, to start searching
       *    after the last keypress?
       *  - treeview has some sort of memoization thing too
       */
      this.setState({searchValue: value})
    } else {
      const filtered =
            allItems.map(
              opt => Object.assign
              ({}, opt)).filter(item => this.filterItems(item, value))
      this.setState({ filteredItems: filtered, isFiltered: true, searchValue: value })
    }
  }

  onSearchClear = () => {
    const { allItems } = this.state
    this.setState({
      filteredItems: allItems,
      isFiltered: false,
      searchValue: ''
    })
  }

  filterItems = (item, input) => {
    if (item.id.toLowerCase().includes(input.toLowerCase())) {
      return true
    }

    if (item.children) {
      return (
        (item.children = item.children
         .map(opt => Object.assign({}, opt))
         .filter(child => this.filterItems(child, input))).length > 0
      )
    }
  };

  setExpanded = () => {
    this.setState({isFiltered: true})
  }

  render () {
    const { tenant } = this.props
    const { filteredItems, isFiltered, searchValue } = this.state

    const toolbar = (
      <Toolbar>
        <ToolbarContent>
          <ToolbarItem variant='label'>
            Job definitions for tenant <Label>{tenant.name}</Label>
          </ToolbarItem>
          <ToolbarItem>
            <SearchInput
              onChange={this.onSearch}
              onClear={this.onSearchClear}
              value={searchValue}
              id='input-search'
              name='search-input-box'
              aria-label='Filter jobs' />
          </ToolbarItem>
          <ToolbarItem variant="separator" />
          <ToolbarItem>
            <Button onClick={this.setExpanded}>Expand all</Button>
          </ToolbarItem>
        </ToolbarContent>
      </Toolbar>
    )

    return (
        <React.Fragment>
        <PageSection>
          <TreeView
            hasBadges data={filteredItems}
            allExpanded={isFiltered}
            toolbar={toolbar}
            hasGuides={true}/>
        </PageSection>
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
}))(JobsList)
