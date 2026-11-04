Configuration
=============

Stanwell uses a YAML configuration file to describe your
working pattern, local database and Toggl connection.

By default, the command-line interface looks for:

.. code-block:: text

   ~/.config/stanwell/config.yaml

A different configuration file can be selected with the global
`--config` (or `-c`) option.

Working pattern
---------------

The configuration describes how the application should interpret your
recorded time. Important settings include:

`workday_hours`
    The number of hours in a standard working day.

`working_days`
    The weekdays on which work is normally required.

`core_start` and `core_end`
    The normal core-hours interval used when analysing working patterns.

`timezone`
    The timezone used when interpreting recorded time.

`tracking_start_date`
    The date from which working-time tracking begins.

For example:

.. code-block:: yaml

   workday_hours: 7.5
   working_days: [0, 1, 2, 3, 4]
   timezone: Europe/London
   core_start: "10:00"
   core_end: "16:00"

Exception days
--------------

Exception days represent dates on which the normal working pattern does not
apply.

The standard exception types are:

`annual_leave`
    Annual leave.

`sick`
    Sick leave.

`public_holiday`
    A public holiday.

`closure_day`
    An organisation closure day.

`overtime_compensation`
    Time taken off in lieu of overtime.

Annual leave, sickness, public holidays and closure days remove the normal
working-time requirement for that day.

Overtime compensation also removes the normal requirement, but differs in
one important respect: the compensated hours are deducted from the accumulated
working-time balance.

This allows a day taken in lieu to offset additional time worked previously,
rather than appearing simply as another non-working day.
