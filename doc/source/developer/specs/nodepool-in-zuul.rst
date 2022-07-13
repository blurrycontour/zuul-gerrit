Nodepool in Zuul
================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.

The following specification describes plan to move Nodepool's
functionality into Zuul and end development of Nodepool as a separate
application.  This will allow for more node and image related features
as well as simpler maintenance and deployment.

Introduction
------------

Nodepool exists as a distinct application from Zuul largely due to
historical circumstances: it was originally a process for launching
nodes, attaching them to Jenkins, detaching them from Jenkins and
deleting them.  Once Zuul grew its own execution engine, Nodepool
could have been adopted into Zuul at that point, but the existing
loose API meant it was easy to maintain them separately and combining
them wasn't particularly advantageous.

However, now we find ourselves with a very robust framework in Zuul
for dealing with ZooKeeper, multiple components, web services and REST
APIs.  All of these are lagging behind in Nodepool, and it is time to
address that one way or another.  We could of course upgrade
Nodepool's infrastructure to match Zuul's, or even separate out these
frameworks into third-party libraries.  However, there are other
reasons to consider tighter coupling between Zuul and Nodepool, and
these tilt the scales in favor of moving Nodepool functionality into
Zuul.

Designing Nodepool as part of Zuul would allow for more features
related to Zuul's multi-tenancy.  Zuul is quite good at
fault-tolerance as well as scaling, so designing Nodepool around that
could allow for better cooperation between node launchers.  Finally,
as part of Zuul, Nodepool's image lifecycle can be more easily
integrated with Zuul-based workflow.

There are two Nodepool components: nodepool-builder and
nodepool-launcher.  We will address the functionality of each in the
following sections on Image Management and Node Management.

This spec contemplates a new Zuul component to handle image and node
management: zuul-launcher.  Much of the Nodepool configuration will
become Zuul configuration as well.  That is detailed in its own
section, but for now, it's enough to know that the Zuul system as a
whole will know what images and node labels are present in the
configuration.

Image Management
----------------

Part of nodepool-builder's functionality is important to have as a
long-running daemon, and part of what it does would make more sense as
a Zuul job.  By moving the actual image build into a Zuul job, we can
make the activity more visible to users of the system.  It will be
easier for users to test changes to image builds (inasmuch as they can
propose a change and a check job can run on that change to see if the
image builds sucessfully).  Build history and logs will be visible in
the usual way in the Zuul web interface.

A frequently requested feature is the ability to verify images before
putting them into service.  This is not practical with the current
implementation of Nodepool because of the loose coupling with Zuul.
However, once we are able to include Zuul jobs in the workflow of
image builds, it is easier to incorporate Zuul jobs to validate those
images as well.  This spec includes a mechanism for that.

The parts of nodepool-builder that makes sense as a long-running
daemon are the parts dealing with image lifecycles.  Uploading builds
to cloud providers, keeping track of image builds and uploads,
deciding when those images should enter or leave service, and deleting
them are all better done with state management and long-running
processes (we should know -- early versions of Nodepool attempted to
do all of that with Jenkins jobs with limited success).

The sections below describe how we will implement image management in
Zuul.

First, a reminder that using custom images is optional with Zuul.
Many Zuul systems will be able to operate using only stock cloud
provider images.  One of the strengths of nodepool-builder is that it
can build an image for Zuul without relying on any particular cloud
provider images.  A Zuul system whose operator wants to use custom
images will need to bootstrap that process, and under the proposed
system where images are build in Zuul jobs, that would need to be done
using a stock cloud image.  In other words, to bootstrap a system such
as OpenDev from scratch, the operators would need to use a stock cloud
image to run the job to build the custom image.  Once a custom image
is available, further image builds could be run on either the stock
cloud image or the custom image.  That decision is left to the
operator and involves consideration of fault tolerance and disaster
recovery scenarios.

To build a custom image, an operator will define a fairly typical Zuul
job for each image they would like to produce.  For example, a system
may have one job to build a debian-stable image, a second job for
debian-unstable, a third job for ubuntu-focal, a fourth job for
ubuntu-jammy.  Zuul's job inheritance system could be very useful here
to deal with many variations of a similar process.

Currently nodepool-builder will build an image under three
circumstances: 1) the image (or the image in a particular format) is
missing; 2) a user has directly requested a build; 3) on an automatic
interval (typically daily).  To map this into Zuul, we will use Zuul's
existing pipeline functionality, but we will add a new trigger for
case #1.  Case #2 can be handled by a manual Zuul enqueue command, and
case #3 by a periodic pipeline trigger.

Since Zuul knows what images are configured and what their current
states are, it will be able to emit trigger events when it detects
that a new image (or image format) has been added to its
configuration.  In these cases, the `zuul` driver in Zuul will enqueue
an `image-build` trigger event on startup or reconfiguration for every
missing image.  The event will include the image name.  Pipelines will
be configured to trigger on `image-build` events as well as on a timer
trigger.

Jobs will include an extra attribute to indicate they build a
particular image.  This serves two purposes; first, in the case of an
`image-build` trigger event, it will act as a matcher so that only
jobs matching the image that needs building are run.  Second, it will
allow Zuul to determine which formats are needed for that image (based
on which providers are configured to use it) and include that
information as job data.

The job will be responsible for building the image and uploading the
result to some storage system.  The URLs for each image format built
should be returned to Zuul as artifacts.

Finally, the `zuul` driver reporter will accept parameters which will
tell it to search the result data for these artifact URLs and update
the internal image state accordingly.

An example configuration for a simple single-stage image build:

.. code-block:: yaml

   - pipeline:
       name: image
       trigger:
         zuul:
           events:
             - image-build
         timer:
           time: 0 0 * * *
       success:
         zuul:
           image-built: true
           image-validated: true

   - job:
       name: build-debian-unstable-image
       image-build-name: debian-unstable

This job would run whenever Zuul determines it needs a new
debian-unstable image or daily at midnight.  Once the job completes,
because of the ``image-built: true`` report, it will look for artifact
data like this:

.. code-block:: yaml

  artifacts:
    - name: raw image
      url: https://storage.example.com/new_image.raw
      metadata:
        type: zuul_image
        image_name: debian-unstable
        format: raw
    - name: qcow2 image
      url: https://storage.example.com/new_image.qcow2
      metadata:
        type: zuul_image
        image_name: debian-unstable
        format: qcow2

Zuul will update internal records in ZooKeeper for the image to record
the storage URLs.  The zuul-launcher process will then start
background processes to download the images from the storage system
and upload them to the configured providers (much as nodepool-builder
does now with files on disk).  As a special case, it may detect that
the image files are stored in a location that a provider can access
directly for import and may be able to import directly from the
storage location rather than downloading locally first.

To handle image validation, a flag will be stored for each image
upload indicating whether it has been validated.  The example above
specifies ``image-validated: true`` and therefore Zuul will put the
image into service as soon as all image uploads are complete.
However, if it were false, then Zuul would emit an `image-validate`
event after each upload is complete.  A second pipeline can be
configured to perform image validation.  It can run any number of
jobs, and since Zuul has complete knowledge of image states, it will
supply nodes using the new image upload (which is not yet in service
for normal jobs).  An example of this might look like:

.. code-block:: yaml

   - pipeline:
       name: image-validate
       trigger:
         zuul:
           events:
             - image-validate
       success:
         zuul:
           image-validated: true

   - job:
       name: validate-debian-unstable-image
       image-build-name: debian-unstable
       nodeset:
         nodes:
           - name: node
             label: debian

The label should specify the same image that is being validated.  Its
node request will be made with extra specifications so that it is
fulfilled with a node built from the image under test.  This process
may repeat for each of the providers using that image (normal pipeline
queue deduplication rules may need a special case to allow this).
Once the validation jobs pass, the entry in ZooKeeper will be updated
and the image will go into regular service.

A more specific process definition follows:

After a buildset reports with ``image-built: true``, Zuul will scan
result data and for each artifact it finds, it will create an entry in
ZooKeeper at `/zuul/images/debian-unstable/<sequence>`.  Zuul will
know not to emit any more `image-build` events for that image at this
point.

For every provider using that image, Zuul will create an entry in
ZooKeeper at
`/zuul/image-uploads/debian-unstable/<image_number>/provider/<provider_name>`.
It will set the remote image ID to null and the `image-validated` flag
to whatever was specified in the reporter.

Whenever zuul-launcher observes a new `image-upload` record without an
ID, it will:

* Lock the whole image
* Lock each upload it can handle
* Unlocks the image while retaining the upload locks
* Downloads artifact (if needed) and uploads images to provider
* If upload requires validation, it enqueues an `image-validate` zuul driver trigger event
* Unlocks upload

The locking sequence is so that a single launcher can perform multiple
uploads from a single artifact download if it has the opportunity.

Once more than two builds of an image are in service, the oldest is
deleted.  The image ZooKeeper record set to the `deleting` state.
Zuul-launcher will delete the uploads from the providers.  The `zuul`
driver emits an `image-delete` event with item data for the image
artifact.  This will trigger an image-delete job that can delete the
artifact from the cloud storage.

All of these pipeline definitions should be in a single tenant, but
the images they build are global (to the extent that any
`allowed-labels` or other similar restrictions permit).  Access to the
repos that participate in that tenant constitutes access to the image
build definitions (since any project in that tenant could attach a job
to the image build pipelines).

Snapshot Images
~~~~~~~~~~~~~~~

Nodepool does not currently support snapshot images, but the spec for
the current version of Nodepool does contemplate the possibility of a
snapshot based nodepool-builder process.  Likewise, this spec does not
require us to support snapshot image builds, but in case we want to
add support in the future, we should have a plan for it.

The image build job in Zuul could, instead of running
diskimage-builder, act on the remote node to prepare it for a
snapshot.  A special job attribute could indicate that it is a
snapshot image job, and instead of having the zuul-launcher component
delete the node at the end of the job, it could snapshot the node and
record that information in ZooKeeper.  Unlike an image-build job, an
image-snapshot job would need to run in each provider (similar to how
it is proposed that an image-validate job will run in each provider).
An image-delete job would not be required.


Node Management
---------------

The techniques we have developed for cooperative processing in Zuul
can be applied to the node lifecycle.  This is a good time to make a
significant change to the nodepool protocol.  We can achieve several
long-standing goals:

* Scaling and fault-tolerance: rather than having a 1:N relationship
  of provider:nodepool-launcher, we can have multiple zuul-launcher
  processes, each of which is capable of handling any number of
  providers.

* More intentional request fulfillment: almost no intelligence goes
  into selecting which provider will fulfill a given node request; by
  assigning providers intentionally, we can more efficiently utilize
  providers.

* Fulfilling node requests from multiple providers: by designing
  zuul-launcher for cooperative work, we can have nodesets that
  request nodes which are fulfilled by different providers.  Generally
  we should favor the same provider for a set of nodes (since they may
  need to communicate over a LAN), but if that is not feasible,
  allowing multiple providers to fulfill a request will permit
  nodesets with diverse node types (e.g., VM + static, or VM +
  container).

Each zuul-launcher process will execute a number of processing loops
in series; first a global request processing loop, and then a
processing loop for each provider.  Each one will involve obtaining a
ZooKeeper lock so that only one zuul-launcher process will perform
each function at a time.

Currently a node request as a whole may be declined by providers.  We
will make that more granular and store information about each node in
the request (in other words, individual nodes may be declined by
providers).

All drivers for providers should implement the state machine
interface.  Any state machine information currently storen in memory
in nodepool-launcher will need to move to ZooKeeper so that other
launchers can resume state machine processing.

The individual provider loop will:
* Lock a provider in ZooKeeper (`/zuul/provider/<name>`)
* Iterate over every node assigned to that provider in a `building` state
  * Drive the state machine
  * If success, update request
  * If failure, determine if it's a temporary or permanent failure
    and update the request accordingly
  * If quota available, unpause provider (if paused)

The global queue process will:
* Lock the global queue
* Iterate over every pending node request, and every node within that request
  * If all providers have failed the request, clear all temp failures
  * If all providers have permanently failed the request, return error
  * Identify providers capable of fulfilling the request
  * Assign nodes to any provider with sufficient quota
  * If no providers with sufficient quota, assign it to first (highest
    priority) provider that can fulfill it later and pause that
    provider

Configuration
-------------

The configuration currently handled by Nodepool will be refactored and
added to Zuul's tenant configuration file.  This means that it will be
non-speculative and not loaded directly from git repos.  Instead it
will be static configuration in the same way that tenants, global
semaphores, and authorization rules are managed.  A reconfiguration
event will be needed to prompt Zuul to reload the configuration file
on updates.

Because the tenant configuration file is becoming larger and has more
types of configuration items in it, we will add support for loading it
from a directory.  This will allow operators to have files such as
`nodes.yaml` and `tenants.yaml`.

The diskimage-builder related configuration items will no longer be
necessary since they will be encoded in Zuul jobs.  This will reduce
the complexity of the configuration significantly.

The `provider` configuration will be similar to what is provided to
nodepool-launcher now, except that we will take the opportunity to
make it more "Zuul-like".  Instead of a top-level dictionary, we will
have a list.  We will standardize on attributes used across drivers
where possible, as well as attributes which may be located at the
label, pool, or provider level.  A configuration may look like:

.. code-block:: yaml

   - label:
       name: debian-unstable
       min-ready: 2

   - image:
       name: debian-unstable

   - provider:
       name: rax-dfw
       driver: openstack
       pools:
         - name: main
           labels:
             - name: debian-unstable
               image: debian-unstable
               flavor: small

Upgrade Process
---------------

Most users of diskimages will need to create new jobs to build these
images.  It would be least disruptive if they could have the new
system building images in parallel with existing systems until ready
to cutover.

However, it would be quite difficult for the new node launching system
to operate at the same time as the current one since we are changing
the format and handling of node requests.

To make the transition minimally disruptive as possible, we should
allow image builds under the new system (but without the validation
step) while node requests are fulfilled by Nodepool.

We should add support for the new node request system but disable it
by default.  When operators are ready, they can shut down Nodepool and
switch a `zuul.conf` configuration flag to enable requests to
zuul-launcher.

We may be able to make that transition seamless (so that old requests
continue to be handled by Nodepool while new requests are handled by
zuul-launcher), but that's not clear at this point, and for a change
like this, a complete Zuul restart is reasonable, so this isn't
considered a hard requirement.

Library Requirements
--------------------

The new zuul-launcher component will need most of Nodepool's current
dependencies, which will entail adding many third-party cloud provider
interfaces.  As of writing, this uses another 420M of disk space.
Since our primary method of distribution at this point is container
images, if the additional space is a concern, we could restrict the
installation of these dependencies to only the zuul-launcher image.

Work Items
----------

* In existing Nodepool convert the following drivers to statemachine:
  gce, kubernetes, openshift, openshift, openstack (openstack is the
  only one likely to require substantial effort, the others should be
  trivial)
* Add roles to zuul-jobs to build images using diskimage-builder
* Update Zuul's main config file to support directories
* Add nodepool config items to main config
* Add nodepool config items to Abide
* Create zuul-launcher executable/component
* Add image-name item data
* Add image-build-name attribute to jobs
  * Including job matcher based on item image-name
  * Include image format information based on global config
* Add zuul driver pipeline trigger/reporter
* Add image lifecycle manager to zuul-launcher
  * Emit image-build events
  * Emit image-validate events
  * Emit image-delete events
* Add Nodepool driver code to Zuul
* Update zuul-launcher to perform image uploads and deletion
* Implement node launch global request handler
* Implement node launch provider handlers
* Update Zuul nodepool interface to handle both Nodepool and
  zuul-launcher node request queues
* Add feature flag to switch bteween them
* Release a minor version of Zuul with support for both
* Remove Nodepool support from Zuul
* Release a major version of Zuul with only zuul-launcher support
* Retire Nodepool
