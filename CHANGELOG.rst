Changelog
=========

Releases are assembled from ``newsfragments/`` using Towncrier.

.. towncrier release notes start

2026.10.6 (2026-10-06)
----------------------

Features
~~~~~~~~

- Add ``coderpad questions variants create`` with optional starter files, JSON
  output containing the new variant ID, and offline dry runs.
  (#22)
- Add question-scoped variant list, get, and delete commands with JSON output.
  Deletion supports a network-free dry run and is never retried.
  (#27)
- Edit variant solutions, environments, structured files, and explicit resets
  with offline JSON plans.
  Variant creation also accepts solution files and structured project overlays.
  (#28)


2026.10.2 (2026-10-02)
----------------------

Features
~~~~~~~~

- Add ``--variant-id`` to ``coderpad questions upload`` for updating existing
  question variants from a UTF-8 file or project directory, with shared source
  selection, credential-free dry runs, and preserved metadata.
  (#16)


2026.10.1 (2026-10-01)
----------------------

Features
~~~~~~~~

- Require Developer ID signing and Apple notarization for standalone macOS
  release binaries, with signature, startup, and online ticket checks before
  publication.
- Upload existing question starter code from an exact UTF-8 file or a filtered
  directory, with offline dry runs and metadata preservation.
