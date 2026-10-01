coderpad-cli
============

Upload starter code to an existing CoderPad Interview question using
``coderpad-py``. This independent CLI preserves titles, descriptions, and
other metadata by updating only the supplied starter-code field.

Requires Python 3.12 or later. No package release has been published yet.
Install the checkout for now:

.. code-block:: console

   uv sync --locked
   uv run coderpad --help
   uv run python -m coderpad_cli --version

After the first PyPI release, install with ``uv tool install coderpad-cli``
or ``pip install coderpad-cli``.

Usage
-----

Use synthetic question ID ``123456`` below in place of your own question ID.
Exactly one content source is required:

.. code-block:: console

   coderpad questions upload 123456 --directory ./starter --dry-run
   coderpad questions upload 123456 --directory ./starter --exclude '*.zip'
   coderpad questions upload 123456 --file ./starter.py

Real uploads read ``CODERPAD_API_KEY`` from the environment. Get a key from
your CoderPad dashboard settings. Missing, empty, and whitespace-only keys
fail clearly. Dry runs need no key and make no network requests.

Single files must be UTF-8. Their text is preserved exactly, including CRLF,
blank lines, trailing whitespace, a UTF-8 BOM, and documentation markers.
Empty files are valid. Neither paths nor IDs are inferred from repository
configuration. Inputs are fully read or staged before a mutation is issued.
Errors exit nonzero; API response bodies and credentials are never printed.
Uploads retain the SDK's retry behavior; the CLI adds no retries.

Directory selection
-------------------

* Both Git and non-Git directories work. Paths are relative to the current
  working directory. A Git worktree's ``.git`` file also identifies its root.
* In a Git repository, rules are inherited from the nearest Git root down
  to the upload directory. Outside Git, rules start at the upload directory;
  unrelated parent ``.gitignore`` files are not used.
* Each traversed directory adds its own ``.gitignore`` rules. Later matching
  rules override earlier ones, and deeper files override ancestor rules.
  Patterns are relative to their owning directory. Directory-only rules and
  negations follow Gitignore semantics. Excluded directories are pruned, so
  a child cannot re-include itself unless its parent is re-included first.
  This also applies to ancestors of an explicitly selected nested upload root.
* Ignore rules apply to tracked files too. Global Git excludes and
  ``.git/info/exclude`` are not read. Hidden files, including ``.gitignore``,
  are uploaded unless excluded.
* ``.git`` files and directories are always excluded at every depth.
  Repeatable ``--exclude PATTERN`` options form a final Gitignore rule layer,
  relative to the upload root. This layer can exclude files re-included by
  ``.gitignore``; its own later negations can undo its earlier patterns.
  It cannot re-include a file excluded by ``.gitignore`` or Git metadata.
* ZIP files are included by default. Use ``--exclude '*.zip'`` to omit them.
  Add other exclusions explicitly, for example ``--exclude node_modules/``.
* Selected symlinks (including directory, broken, and external links) and
  symlinks in the source path are rejected rather than dereferenced. Ignored
  links are skipped. Symlinked ``.gitignore`` files are rejected when their
  rules would be read. Special files are rejected. Empty selections fail.
  File bytes are copied to a temporary directory, and the SDK independently
  validates and serializes that directory using its ZIP importer.

Development and distribution
----------------------------

See ``docs/source/development.rst`` for checks, release setup, and local
Docker, standalone binary, and Nix builds. The generated CLI reference is
in ``docs/source/cli.rst``. There are no prebuilt artifacts yet.

See ``docs/source/migration.rst`` for migrating an existing shell uploader
and keeping repository-specific snippet preparation outside this CLI.
