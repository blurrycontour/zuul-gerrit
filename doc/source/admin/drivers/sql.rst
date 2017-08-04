:title: SQL Driver

SQL
===

The SQL driver supports reporters only.  Only one connection per
database is permitted.

Connection Configuration
------------------------

The connection options for the SQL driver are:

.. attr:: <sql connection>

   .. attr:: driver
      :required:

      .. value:: sql

         The connection must set ``driver=sql`` for SQL connections.

   .. attr:: dburi
      :required:

      Database connection information in the form of a URI understood
      by SQLAlchemy.  See `The SQLAlchemy manual
      <http://docs.sqlalchemy.org/en/rel_1_0/core/engines.html#database-urls>`_
      for more information.

Reporter Configuration
----------------------

This reporter is used to store results in a database.

A :ref:`connection<connections>` that uses the sql driver must be
supplied to the reporter.

``zuul.conf`` contains the database connection and credentials. To
store different reports in different databases you'll need to create a
new connection per database.

The SQL reporter does nothing on :attr:`pipeline.start` or
:attr:`pipeline.merge-failure`; it only acts on
:attr:`pipeline.success` or :attr:`failure` reporting stages.

For example ::

  - pipeline:
      name: post-merge
      success:
        mydb_conn:
            score: 1
      failure:
        mydb_conn:
            score: -1

.. attr:: pipeline.<reporter>.<sql source>

   To report to a database, the dictionaries passed to the pipeline
   :ref:`reporter<reporters>` attributes support the following
   attributes:

   .. attr:: score

      A score to store for the result of the build. eg: -1 might
      indicate a failed build.
