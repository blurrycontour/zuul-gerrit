:orphan:

Install Mysql
================

Installation
-------------

Install `MySQL
<https://www.digitalocean.com/community/tutorials/how-to-install-mariadb-on-centos-7/>`_
server and set it to auto start on boot.

.. code-block:: shell

    sudo dnf install mariadb-server # Install DB
    sudo systemctl enable mariadb # Enable DB service start on reboot
    sudo systemctl start mariadb # Start DB service
    sudo dnf install python3-PyMySQL.noarch # Lib for zuul sql driver interract with DB

Configuration
------------

Start `MySQL` as administrator by running:

.. code-block:: shell

    sudo sudo mysql

Create user zuul. Create database zuul. Grant user zuul privileges to operate over zuul database.

.. code-block:: shell

    CREATE USER 'zuul'@'localhost' IDENTIFIED BY 'secret';
    CREATE DATABASE zuul;
    GRANT ALL ON zuul.* TO 'zuul'@'localhost';

Leave `MySQL` CLI by typing:

.. code-block:: shell

    exit

.. note:: Make sure that credentials here are exactly the same as in one
	provided in /etc/zuul/zuul.conf in section `mysql`
