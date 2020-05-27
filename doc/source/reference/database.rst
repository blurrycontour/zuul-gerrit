:title: Database Configuration

.. _database:

Database Configuration
======================

The database configuration is located in the ``database`` section of
``zuul.conf``:

.. code-block:: ini

  [database]
  dburi=<URI>

The following options can be defined in this section.

.. attr:: database

   .. attr:: dburi
      :required:

      Database connection information in the form of a URI understood
      by SQLAlchemy.  See `The SQLAlchemy manual
      <https://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls>`_
      for more information.

      The driver will automatically set up the database creating and managing
      the necessary tables. Therefore the provided user should have sufficient
      permissions to manage the database. For example:

      .. code-block:: sql

        GRANT ALL ON my_database TO 'my_user'@'%';

   .. attr:: pool_recycle
      :default: 1

      Tune the pool_recycle value. See `The SQLAlchemy manual on pooling
      <http://docs.sqlalchemy.org/en/latest/core/pooling.html#setting-pool-recycle>`_
      for more information.

   .. attr:: table_prefix
      :default: ''

      The string to prefix the table names. This makes it possible to run
      several zuul deployments against the same database. This can be useful
      if you rely on external databases which are not under your control.
      The default is to have no prefix.
