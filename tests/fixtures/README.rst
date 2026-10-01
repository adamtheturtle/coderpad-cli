Question upload contract fixture
================================

``question-upload.openapi.json`` is a reduced snapshot of ``openapi.json``
from ``coderpad-py`` release ``2026.10.01.1``, commit
``d36db633f46e068ea33370d234d76b8cbecf8cde``:

https://github.com/adamtheturtle/coderpad/blob/d36db633f46e068ea33370d234d76b8cbecf8cde/openapi.json

Source SHA-256:
``7e0533867d8ad85b0725e2c45b84f0085ec907e4930eea94a8c34f51440baf2b``.

The retained data is the
question PUT operation's request body, its synthetic success response, and
the referenced ``QuestionForm`` component. These sections are unchanged;
only unrelated operations, examples, headers, and prose are omitted. The
fixture's title and version identify its purpose and SDK baseline.

The canonical specification remains in the SDK repository. Refresh this
fixture from a reviewed SDK release when its upload contract changes. Review
that diff alongside the SDK dependency update. Tests never download the spec
and never contact a real CoderPad server.

The contract checks request shape. Synthetic state in the tests checks that
starter code changes while existing metadata is preserved. Neither is a
claim that a mock independently proves undocumented live API behavior.

This test data is derived from the SDK repository under its MIT license,
Copyright (c) Adam Dangoor. The license is reproduced at the repository root.
