Projects and tags in Toggl
==========================

Stanwell can use the projects and tags associated with your Toggl time
entries to explore how your working time is distributed.

There is no required classification scheme. The examples on this page
illustrate how Stanwell interprets projects and tags and the kinds of
analysis that become possible when they are used consistently.

Projects and tags provide two complementary ways of describing a time
entry:

* projects identify the project or work stream associated with the entry;
* tags can describe the type of activity carried out.

This means that a project answers a question such as *"What am I working
on?"*, while tags can answer *"What kind of work am I doing?"*.


Projects
--------

Projects are useful for representing relatively broad and stable areas of
work or work streams.

For example:

* ``Admin``
* ``Project A``
* ``Project B``
* ``Teaching``
* ``Professional development``

A time entry would normally belong to one project.

For example:

.. list-table::
   :header-rows: 1
   :widths: 60 30

   * - Description
     - Project
   * - Prepare project update
     - Project A
   * - Review student documentation
     - Teaching
   * - Process expenses
     - Admin

Stanwell uses projects to show how working time is distributed across
different areas of work. This can help answer questions such as:

* How much of my time goes to each project or work stream?
* How many hours have I spent on a project?
* How many equivalent working days does this represent?
* How does my allocation of time differ between projects?

The project names themselves are not significant to Stanwell. What matters
is that entries belonging to the same area of work use the same project.


Tags
----

Tags provide another dimension. They can represent the type of activity
associated with a time entry.

For example:

* ``meeting``
* ``seminar``
* ``emails``
* ``programming``
* ``writing``
* ``admin``
* ``planning``

Unlike projects, a time entry can have more than one tag.

For example:

.. list-table::
   :header-rows: 1
   :widths: 45 25 30

   * - Description
     - Project
     - Tags
   * - Project meeting
     - Project A
     - ``meeting``
   * - Write project software
     - Project A
     - ``programming``
   * - Prepare seminar
     - Teaching
     - ``seminar``, ``writing``
   * - Emails about Project B
     - Project B
     - ``emails``, ``admin``

This makes it possible to examine an activity across different projects.
For example, the ``meeting`` tag can show how much time is spent in
meetings regardless of whether those meetings concern Project A, Project B
or administration.

Similarly, a ``programming`` tag can show programming time across several
different projects without requiring programming itself to be represented
as a project.


Choosing useful tags
--------------------

Stanwell does not require a particular set of tags. Tags become useful when
they represent distinctions that you may subsequently want to explore.

For example:

``emails``
   How much working time is spent reading or responding to email? Is this
   proportion changing over time?

``meeting``
   How much time is spent in meetings across different projects?

``seminar``
   How much time is associated with attending or delivering seminars?

``programming``
   How much working time is spent programming, and how does this change
   over time?

``writing``
   How much working time is spent writing, regardless of the project for
   which the writing is being done?

The dashboard can show both the number of hours carrying a selected tag and
the proportion of total working time associated with it. It can also show
how that proportion changes over time.

This means that tags are most useful when they correspond to questions that
you might genuinely want to ask about your working pattern. There is little
benefit in creating additional tags simply because an activity *could* be
classified more precisely.


Projects and tags together
--------------------------

Projects and tags are most useful when they describe different aspects of
the same entry.

For example:

.. code-block:: text

   Description: Implement data import
   Project:     Project A
   Tags:        programming

and:

.. code-block:: text

   Description: Discuss data import
   Project:     Project A
   Tags:        meeting

both represent work on Project A, but distinguish two different kinds of
activity.

Conversely:

.. code-block:: text

   Description: Implement data import
   Project:     Project A
   Tags:        programming

and:

.. code-block:: text

   Description: Improve reporting tool
   Project:     Project B
   Tags:        programming

belong to different projects but both contribute to an analysis of
programming time.

A useful way to think about the distinction is therefore:

**What am I working on?**
   The project or work stream.

**What am I doing?**
   The activity represented by one or more tags.


Overlapping tags
----------------

Tags are not treated as mutually exclusive categories.

For example, an hour-long entry might be tagged with both ``meeting`` and
``admin``. It remains one hour of working time, but it can legitimately
contribute to analyses of both meeting time and administrative activity.

As a result, percentages for several tags should not necessarily be
expected to add up to 100%.

For example:

.. code-block:: text

   Meeting       22% of working time
   Admin         18% of working time
   Emails        10% of working time

does not imply that these activities account for exactly 50% of working
time. Some entries may carry more than one of these tags.

The tag analysis in the dashboard includes an overlap view to make these
intersections visible. This shows the amount of time associated with exact
combinations of selected tags without counting a time entry more than once
within an intersection.


Entries without tags
--------------------

Not every time entry needs to have a tag.

An entry without a tag still contributes to total working time and to its
project. It simply does not contribute to analysis of a particular tagged
activity.

For example, if 7 hours of a 35-hour working week carry the ``emails`` tag,
Stanwell can report that email-related work represented 20% of the week's
recorded working time. The other 28 hours do not need to be assigned to
some alternative tag for this calculation to be meaningful.

This makes it possible to introduce tags selectively for activities that
you are interested in monitoring rather than requiring every minute of work
to fit into a complete activity taxonomy.
