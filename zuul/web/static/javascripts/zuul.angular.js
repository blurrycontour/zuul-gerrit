// @licstart  The following is the entire license notice for the
// JavaScript code in this page.
//
// Copyright 2017 Red Hat
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

angular.module('zuulTenants', []).controller(
    'mainController', function($scope, $http)
{
    $scope.tenants = undefined;
    $scope.tenants_fetch = function() {
        $http.get("tenants.json")
            .then(function success(result) {
                $scope.tenants = result.data;
            });
    }
    $scope.tenants_fetch();
});

angular.module('zuulProjects', []).controller(
    'mainController', function($scope, $http)
{
    $scope.projects = undefined;
    $scope.projects_fetch = function() {
        $http.get("projects.json")
            .then(function success(result) {
                $scope.projects = result.data;
            });
    }
    $scope.projects_fetch();
});

angular.module('zuulProject', [], function($locationProvider) {
    $locationProvider.html5Mode({
        enabled: true,
        requireBase: false
    });
}).controller('mainController', function($scope, $http, $location)
{
    var query_args = $location.search();
    $scope.project_name = query_args["project_name"];
    if (!$scope.project_name) {
        $scope.project_name = "config-projects";
    }
    $scope.project = undefined;
    $scope.graph = undefined;
    $scope.project_fetch = function() {
        $http.get("projects/" + $scope.project_name + ".json")
            .then(function success(result) {
                $scope.project = result.data;
            });
    }
    $scope.project_fetch();
    $scope.toggleGraph = function() {
        $("#projectTable").toggle();
        $("#projectGraph").toggle();
        if (!$scope.graph) {
            $scope.graph = projectGraph($scope.project);
        }
    }
});

function projectGraph(project) {
    var nodes = [];
    var links = [];
    var tips = [];
    ["check", "gate", "post", "release", "tag"].forEach(function(pipeline) {
        if (project.pipelines[pipeline]) {
            // Add pipeline and link it to previs last jobs (tips)
            nodes.push({"id": pipeline, "group": "pipeline"});
            tips.forEach(function(tip) {
                links.push({"source": tip, "target": pipeline})
            });
            tips = [pipeline];
            var local_jobs = [];
            var inter_jobs = [];
            project.pipelines[pipeline].jobs.forEach(function(job) {
                if (job.dependencies.length == 0) {
                    job.dependencies = tips.slice(0);
                } else {
                    job.dependencies.forEach(function(interJob) {
                        inter_jobs.push(interJob);
                    });
                }
                local_jobs.push(job);
            });
            // Find new tip and push job to flow
            tips.length = 0;
            local_jobs.forEach(function(job) {
                job_name = pipeline + "-" + job.name;
                nodes.push({"id": job_name, "group": pipeline});
                job.dependencies.forEach(function(parent) {
                    if (parent == pipeline) {
                        parent_name = pipeline;
                    } else {
                        parent_name = pipeline + "-" + parent;
                    }

                    links.push({"source": parent_name,
                                "target": job_name})
                })
                var found = false;
                for (inter_pos = 0;
                     inter_pos < inter_jobs.length;
                     inter_pos += 1) {
                    if (job.name == inter_jobs[inter_pos]) {
                        found = true;
                        break
                    }
                };
                if (found == false) {
                    tips.push(job_name);
                }
            });
        }
    });
    console.log("nodes", nodes);
    console.log("links", links);
    renderProjectGraph(nodes, links);
}



angular.module('zuulJobs', []).controller(
    'mainController', function($scope, $http)
{
    $scope.jobs = undefined;
    $scope.graph = undefined;
    $scope.jobs_fetch = function() {
        $http.get("jobs.json")
            .then(function success(result) {
                $scope.jobs = result.data;
                $scope.jobs.forEach(function(job){
                    job.expanded = false;
                    job.details = undefined;
                });
            });
    }
    $scope.jobs_fetch();
    $scope.job_fetch = function(job) {
        if (!job.details) {
            $http.get("jobs/" + job.name + ".json")
                .then(function success(result) {
                    job.details = result.data;
                });
        }
        job.expanded = !job.expanded;
    }
    $scope.toggleGraph = function() {
        $("#jobTable").toggle();
        $("#jobGraph").toggle();
        if (!$scope.graph) {
            $scope.graph = jobsGraph($scope.jobs);
        }
    }
});

angular.module('zuulJob', [], function($locationProvider) {
    $locationProvider.html5Mode({
        enabled: true,
        requireBase: false
    });
}).controller('mainController', function($scope, $http, $location)
{
    var query_args = $location.search();
    $scope.job_name = query_args["job_name"];
    if (!$scope.job_name) {
        $scope.job_name = "base";
    }
    $scope.labels_color = new Map();
    $scope.variants = undefined;
    $scope.job_fetch = function() {
        $http.get("jobs/" + $scope.job_name + ".json?full=1")
            .then(function success(result) {
                $scope.variants = result.data;
                $scope.variants.forEach(function(variant){
                    if (Object.keys(variant.variables).length === 0) {
                        variant.variables = undefined;
                    } else {
                        variant.variables = JSON.stringify(
                            variant.variables, undefined, 2);
                    }
                    if (variant.nodeset.length >= 0) {
                        // Generate color based on node label
                        variant.nodeset.forEach(function(node){
                            var hash = 0;
                            for (var idx = 0; idx < node[0].length; idx++) {
                                var c = node[0].charCodeAt(idx);
                                hash = ((hash << 5) - hash) + c;
                                hash = hash & hash;
                            }
                            var r = (0x300000 + hash) & 0xFF0000;
                            var g = (0x005000 + hash) & 0x00FF00;
                            var b = (0x000030 + hash) & 0x0000FF;
                            $scope.labels_color[node[0]] = '#' + (r|g|b).toString(16);

                        });
                    }
                    if (variant.parent == "None") {
                        variant.parent = "base";
                    }
                });
            });
    };
    $scope.job_fetch()
});

angular.module('zuulBuilds', [], function($locationProvider) {
    $locationProvider.html5Mode({
        enabled: true,
        requireBase: false
    });
}).controller('mainController', function($scope, $http, $location)
{
    $scope.rowClass = function(build) {
        if (build.result == "SUCCESS") {
            return "success";
        } else {
            return "warning";
        }
    };
    var query_args = $location.search();
    var url = $location.url();
    var tenant_start = url.lastIndexOf(
        '/', url.lastIndexOf('/builds.html') - 1) + 1;
    var tenant_length = url.lastIndexOf('/builds.html') - tenant_start;
    $scope.tenant = url.substr(tenant_start, tenant_length);
    $scope.builds = undefined;
    if (query_args["pipeline"]) {$scope.pipeline = query_args["pipeline"];
    } else {$scope.pipeline = "";}
    if (query_args["job_name"]) {$scope.job_name = query_args["job_name"];
    } else {$scope.job_name = "";}
    if (query_args["project"]) {$scope.project = query_args["project"];
    } else {$scope.project = "";}
    $scope.builds_fetch = function() {
        query_string = "";
        if ($scope.tenant) {query_string += "&tenant="+$scope.tenant;}
        if ($scope.pipeline) {query_string += "&pipeline="+$scope.pipeline;}
        if ($scope.job_name) {query_string += "&job_name="+$scope.job_name;}
        if ($scope.project) {query_string += "&project="+$scope.project;}
        if (query_string != "") {query_string = "?" + query_string.substr(1);}
        $http.get("builds.json" + query_string)
            .then(function success(result) {
                for (build_pos = 0;
                     build_pos < result.data.length;
                     build_pos += 1) {
                    build = result.data[build_pos]
                    if (build.node_name == null) {
                        build.node_name = 'master'
                    }
                    /* Fix incorect url for post_failure job */
                    if (build.log_url == build.job_name) {
                        build.log_url = undefined;
                    }
                }
                $scope.builds = result.data;
            });
    }
    $scope.builds_fetch()
});
