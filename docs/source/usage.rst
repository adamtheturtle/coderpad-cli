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
