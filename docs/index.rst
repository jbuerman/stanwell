Stanwell
========

*Have enthusiasm. Work sustainably.*

Stanwell helps you understand not only how much you work,
but how your working time is distributed.

The application uses time recorded in `Toggl <https://toggl.com/>`_ to maintain a local record of
working time and provides tools for exploring working-time balance, working
patterns, projects and tagged activities. The aim is to make patterns that
are difficult to see in individual time entries easier to understand.

Stanwell distinguishes between recorded working time and the hours you are
expected to work, allowing the balance between the two to be followed over
time. Non-working days such as annual leave, public holidays and
organisation closure days can be recorded as exceptions. Overtime
compensation is also represented so that time taken off in lieu reduces an
accumulated positive balance.

There are two main ways to interact with Stanwell:

* the command-line interface, used to initialise the application,
  synchronise Toggl data and launch the dashboard;
* the interactive dashboard, used to explore working time, working patterns,
  projects and tagged activities.

Getting started
---------------

If this is your first time using Stanwell, start with
:doc:`getting_started`.
It is also worth reading :doc:`toggl` for an
explanation of how Stanwell uses Toggl projects and tags when analysing your
working time.
Once the application is running, see :doc:`configuration` to
adapt it to your working pattern.

.. toctree::
   :maxdepth: 2
   :caption: User guide
   :titlesonly:

   getting_started
   toggl
   configuration
   cli
   dashboard

.. toctree::
   :maxdepth: 2
   :caption: Reference
   :titlesonly:

   api/index
   changelog