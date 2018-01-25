// @licstart  The following is the entire license notice for the
// JavaScript code in this page.
//
// This module is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This software is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this software.  If not, see <http://www.gnu.org/licenses/>.
// @licend  The above is the entire license notice
// for the JavaScript code in this page.

// Modified from https://bl.ocks.org/mbostock/4063570
function jobsGraph(jobs) {
    var w = d3.select("#jobGraph").attr("width");
    var h = d3.select("#jobGraph").attr("height");
    var vis = d3.select("#jobGraph").append("g").attr(
        "transform", "translate(40,0)");

    var stratify = d3.stratify()
        .id(function(d) {return d.name})
        .parentId(function(d) {if (d.name == "base") {return "";}
                               return d.parent});

    var tree = d3.cluster().size([h, w - 250]);

    var root = stratify(jobs);

    tree(root)

    var link = vis.selectAll(".link")
        .data(root.descendants().slice(1))
        .enter().append("path")
        .attr("class", "link")
        .attr("d", function(d) {
            return "M" + d.y + "," + d.x
                + "C" + (d.parent.y + 100) + "," + d.x
                + " " + (d.parent.y + 100) + "," + d.parent.x
                + " " + d.parent.y + "," + d.parent.x;
        });

    var node = vis.selectAll(".node")
        .data(root.descendants())
        .enter().append("g")
        .attr("transform", function(d) {
            return "translate(" + d.y + "," + d.x + ")"; })

    node.append("circle").attr("r", 2);

    node.append("svg:a")
        .attr("xlink:href", function(d) {
            return "job.html?job_name=" + d.id})
        .append("text")
        .attr("dy", 3)
        .attr("x", function(d) { return d.children ? -8 : 8; })
        .style("text-anchor", function(d) {
            return d.children ? "end" : "start"; })
        .text(function(d) {return d.id});
    return vis;
}
