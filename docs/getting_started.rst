Getting started
===============

Stanwell analyses time entries recorded in
`Toggl <https://toggl.com/>`_. Before initialising the application, you will
need:

* a Toggl API token;
* the ID of the Toggl workspace containing your time entries.

Getting your Toggl API token
----------------------------

Your API token is available from your Toggl profile settings.

Open your Toggl profile settings and find the ``API Token`` section.
Generate a token if necessary and copy it somewhere safe. The token provides
access to your Toggl data, so it should be kept private.

Finding your workspace ID
-------------------------

Stanwell can find the workspace ID for you. Run:

.. code-block:: console

   stanwell toggl-workspaces

If you have not configured an API token yet, the command will prompt you for
one.

The command lists the Toggl workspaces available to your account together
with their IDs. Make a note of the ID for the workspace containing the time
entries you want to analyse.

Initialising Stanwell
---------------------

You can now initialise the application:

.. code-block:: console

   stanwell init

The setup will ask for your:

* Toggl API token;
* Toggl workspace ID;
* hours in a standard working day;
* core working hours;
* date from which working-time tracking should begin.

The command creates the configuration file and initialises the local
database.

Using projects and tags
-----------------------

Stanwell can analyse both projects and tags. A consistent approach to these
makes the resulting dashboard substantially more useful.

As a general rule:

* **projects describe what you are working on**;
* **tags describe what kind of activity you are doing**.

For example, you might use projects such as ``Admin``, ``Project A`` and
``Project B``, while using tags such as ``meeting``, ``seminar``,
``emails``, ``programming`` and ``writing``.

A time entry might therefore look like:

.. code-block:: text

   Description: Implement data import
   Project:     Project A
   Tags:        programming

while another entry in the same project could be:

.. code-block:: text

   Description: Discuss data import
   Project:     Project A
   Tags:        meeting

See :doc:`toggl` for more detailed guidance on structuring projects and tags.

Downloading your Toggl data
---------------------------

Once the application has been initialised, download your existing Toggl
data:

.. code-block:: console

   stanwell sync-missing

This downloads data for dates that are not already stored in the local
database.

You can check the contents of the local database with:

.. code-block:: console

   stanwell status

Opening the dashboard
---------------------

Start the interactive dashboard with:

.. code-block:: console

   stanwell dashboard

The dashboard provides views of your working-time balance, project
allocation, working patterns and tagged activities.

Editing the configuration
-------------------------

You can open the configuration file in your system's default application
with:

.. code-block:: console

   stanwell config

See :doc:`configuration` for an explanation of the available settings.

Next steps
----------

* See :doc:`toggl` for guidance on organising projects and tags.
* See :doc:`configuration` to adapt Stanwell to your working pattern and
  configure exception days.
* See :doc:`cli` for an overview of the command-line interface.
* See :doc:`dashboard` to understand the dashboard views.
