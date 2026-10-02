Question upload contract
========================

Contract tests read the full ``spec/openapi.json`` from the pinned ``spec`` Git
submodule, rather than maintaining a reduced copy here.
The canonical specification is maintained in `coderpad-openapi`_.
The Git tree records the exact commit used by this consumer.
The initial pin is ``e1d67d75cc8fde40ee1f0f382793b2172302c6e3``.
Its ``QuestionForm`` schema is unchanged from the previous fixture.
The full document also supplies the question variant schemas.

.. _coderpad-openapi: https://github.com/adamtheturtle/coderpad-openapi

Prepare the specification before running tests:

.. code-block:: shell

   git submodule update --init spec

To update it, first merge contract changes in the shared repository, then check
out a reviewed full commit SHA in ``spec`` and commit the new Git pin:

.. code-block:: shell

   git -C spec fetch origin
   git -C spec checkout REVIEWED_COMMIT_SHA
   git add spec
   uv run --locked pytest tests/test_http_contract.py --no-cov

Review the upstream contract diff alongside the relevant SDK dependency changes
before committing the pin.
Never edit a separate contract copy in this repository.
CI initializes the submodule during checkout.
Tests never download the specification or contact a real CoderPad server.
Source distributions include the document and its MIT license so their contract
tests do not need Git metadata.

The contract checks request shape.
Synthetic state in the tests checks that starter code changes while existing
metadata is preserved.
Neither is a claim that a mock independently proves undocumented live API
behavior.
Keep those assertions here, not in the shared specification.

The shared repository preserves the original MIT license and attribution in
``spec/LICENSE``.
