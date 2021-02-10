Building Nodepool Images in Zuul
================================

.. warning:: This is not authoritative documentation.  These features
   are not currently available in Zuul.  They may change significantly
   before final implementation, or may never be fully completed.


Background
----------

Diskimage-builder (DIB) is great for building GNU/Linux images, but
does not support Windows or container images.  We would like to
continue to use DIB, while also supporting other methods of building
images.

Building images within Zuul jobs allows for considerable flexibility
in how the image build is accomplished, as well as offering visibility
and consistency to contributors.

This spec aims to describe two methods of using Zuul to build images
and how to integrate that process with Nodepool.

Currently no changes to the existing nodepool-builder use of DIB is
contemplated.


Proposed Change
---------------

Two approaches are described.  The main difference between them is
where the responsibility for *deleting* images lies.  First, the
approach where Zuul jobs delete images:

Zuul Deletes Images
~~~~~~~~~~~~~~~~~~~

* A Zuul job builds an image.
* The same or a dependent Zuul job uploads the image to the cloud.
* Nodepool-launcher is configured to use image-filters with a
  cloud-image stanza in order to identify the most recent image and
  use that when launching instances.
* A Zuul job will need to delete old versions of images, as well as
  detect and clean up any leaked resources due to errors or aborted
  builds.  This could be a separate job, or it could simply run at the
  start of the image build job.

The advantage of this method is that almost all of the image lifecycle
is in Zuul jobs which means more visibility.  The disadvantage is that
means we lose the significant logic in Nodepool to handle retries and
cleanups, especially around image uploads.

This approach may be appropriate for lightweight systems where risks
of build or upload failures are limited therefore requiring little
additional logic, but may not be appropriate for more complex
environments.

The only change needed to support this is to ensure that all relevant
drivers have an `image-filters`_ option similar to the AWS driver.
Ansible roles supporting this will be welcome in the zuul-jobs repo.
Roles to build images should be kept separate from supporting roles
implementing image lifecycle management so that they can be shared
with the option below.

.. _image-filters: https://zuul-ci.org/docs/nodepool/aws.html#attr-providers.[aws].cloud-images.image-filters

Nodepool Deletes Images
~~~~~~~~~~~~~~~~~~~~~~~

* A Zuul job builds an image.
* Nodepool-builder queries the Zuul API to find successful builds of
  the image, downloads the image file indicated by an artifact URL for
  the image, and then uploads that file to clouds in the same way it
  would a file created by DIB.
* Nodepool-launcher launches Nodepool-managed images as normal.
* Nodepool-builder deletes Nodepool-managed images as normal.

The advantage here is that nearly the entire image lifecycle
management remains under nodepool-builder's control.  As compared to a
nodepool-builder spawned DIB build today, the main difference is that
Zuul would control the timing of the image build.  The disadvantage is
that the upload and delete phases of the lifecycle will remain less
accessible to non-administrators.

To implement this change, we could add new configuration options to
nodepool builder; in addition to `diskimages` and `cloud-images`, we
will add `zuul-images`:

.. code-block:: yaml

   zuul-images:
     api-url: https://zuul.example.com/
     project: opendev/system-config
     pipelines:
       - periodic
       - post
     job: build-ubuntu-focal-image
     artifacts:
       - format: qcow
         type: image-qcow
       - format: raw
         type: image-raw

That would instruct nodepool-builder to, instead of launching
`disk-image-create` to build an image, query the Zuul API for builds
of the job specified, and if there is a new build since the last run,
download the files specified by the artifacts section.  This section
maps Zuul artifacts to image formats.  Nodepool-builder knows which
formats it needs for an image based on the providers to which it will
upload; the same will be true here, so it will only download the raw
image if necessary.

After downloading, the appropriate image files will be on disk on the
nodepool-builder node, and the existing upload and delete code can
work with this system unchanged.

We would likely have the poll run frequently in order to pick up new
image builds quickly.  We will also need to add configuration options
for authenticating to the Zuul API for systems that require it.

Challenges
----------

Any resources that are created during the image build job will still
need to be cleaned up within that job (as is true for any Zuul job).
If image builds happen entirely on an ephemeral node, this is no
problem.  But if the job creates its own VM snapshots in a cloud or
other similar external resources, the job will need to handle cleaning
up leaks.
