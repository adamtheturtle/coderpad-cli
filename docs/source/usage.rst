.. include:: ../../README.rst

Variant discovery and deletion
------------------------------

List variants or inspect one as JSON to recover its ID and template identity:

.. code-block:: console

   $ coderpad questions variants list 123456
   $ coderpad questions variants get 123456 7

Delete a variant with an explicit command.
A dry run prints the target IDs without credentials or network access:

.. code-block:: console

   $ coderpad questions variants delete 123456 7 --dry-run
   $ coderpad questions variants delete 123456 7

Deletion affects only the selected variant.
It does not delete the parent question or retry automatically.

Explicit variant edits
----------------------

Use ``questions variants update QUESTION_ID VARIANT_ID`` to change selected
variant fields.
Options include ``--language``, ``--solution-file``, ``--file``,
``--directory``, and ``--file-contents-json``.
Creation also accepts ``--solution-file`` and ``--file-contents-json``.

Omitted content stays omitted.
An empty UTF-8 source file writes blank code.
``--reset-code`` sends explicit null to restore single-file defaults.
``--reset-project`` sends an empty file list to restore the project template.
Changing language or template clears existing code unless replacement code is
supplied.
The starter-only ``questions upload --variant-id`` command keeps its existing
behavior.

Project JSON is an array of file objects with ``path``, optional ``contents``,
``hidden``, and ``deleted``.
Path-only removal entries retain omitted contents.
An empty JSON array also restores the project template.
On creation, overlays layer over template files.
On update, they replace the file list.
The ``.cpad`` directory cannot be deleted.

All local inputs are validated before a mutation.
Content inputs and reset flags are mutually exclusive.
``--dry-run`` prints a JSON plan without keys or network access.
Updates and creation are never automatically retried.

.. code-block:: sh

    coderpad questions variants update 123456 7 --solution-file solution.py
    coderpad questions variants update 123456 7 --reset-project --dry-run
    coderpad questions variants update 123456 7 --file-contents-json files.json
    coderpad questions variants create 123456 --language python3 --solution-file solution.py
