Changelog
=========

Releases are assembled from ``newsfragments/`` using Towncrier.

.. towncrier release notes start

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
