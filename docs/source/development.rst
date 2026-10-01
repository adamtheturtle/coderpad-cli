Development and releases
========================

This repository follows the current main branch of ``literalizer-cli``
(inspected at ``cf435b8ee67dd9900d795a8438622ad02aaaf730``). It adapts its src
layout, Click entry points, setuptools-scm versions, uv lockfile, strict
checks, branch coverage, Sphinx, Towncrier, and distribution builds. It does
not inherit conversion features, historical release notes, checker exceptions,
Homebrew or winget publication, signing secrets, or unavailable artifact links.
The SDK baseline is the released ``coderpad-py==2026.10.1.1`` in ``uv.lock``.

.. code-block:: shell

   uv sync --locked --group dev
   uv run pytest
   uv run prek run --all-files
   uv run prek run --all-files --stage pre-push
   uv run sphinx-build -W --keep-going -b html docs/source docs/build/html
   uv build
   uv run twine check dist/*
   uv run check-wheel-contents dist/*.whl

Tests use the real SDK with its public ``Transport`` interface. No SDK methods
are replaced, no live questions are mutated, and production adds no retry
policy. Synthetic transports assert the exact mutation payload, including the
absence of title, description, language, solution, and instruction fields.
Additional contract tests exercise the SDK's default HTTPX transport through
RESPX. They validate form and multipart fields against a pinned, reduced
OpenAPI fixture from the SDK, inspect the SDK-generated ZIP bytes, and verify
that metadata is absent from the outgoing update. The mock rejects every
unregistered request. No SDK methods are replaced. See
``tests/fixtures/README.rst`` for the fixture's source and update policy.

The SDK remains the canonical owner of its OpenAPI contract. A separate spec
repository would add a release and synchronization boundary without improving
these upload tests. Consider extracting it if several independently versioned
clients need a shared contract with its own maintainers and release policy.

Add a Towncrier feature or bugfix fragment for each user-visible change.

Versions derive from Git tags using setuptools-scm. Untagged initial builds
have a development version. Use date-based tags such as ``2026.10.02`` for
releases; no release tag is created as part of repository initialization.
Before tagging a release, assemble notes with
``uv run towncrier build --yes --version VERSION``, commit the changelog, then
write the same version to ``VERSION``, commit it, then tag the commit.
Pushing a tag is the explicit publication trigger. The release
workflow builds and checks packages, builds three standalone binaries, and
then publishes to PyPI, GitHub Releases, and GHCR.

Local builds
------------

.. code-block:: shell

   uv run --group binary pyinstaller --clean --onefile --copy-metadata coderpad-cli --name coderpad bin/coderpad_wrapper.py
   ./dist/coderpad --help
   docker build -t coderpad-cli .
   docker run --rm coderpad-cli --help
   nix flake check
   nix build
   nix run . -- --help

The Docker image builds a wheel from this checkout rather than depending on
an unpublished PyPI artifact. Mount content read-only and forward the existing
environment variable for an upload:

.. code-block:: shell

   docker run --rm -e CODERPAD_API_KEY -v "$PWD/starter:/starter:ro" coderpad-cli questions upload 123456 --directory /starter --dry-run

The Nix flake uses uv2nix and the committed lockfiles. Its build injects an
SCM version because Git metadata is unavailable in Nix source snapshots.
Standalone macOS builds are unsigned; distribution signing and notarization
can be added after configuring the owner's Apple credentials.

External setup
--------------

* Register a PyPI trusted publisher for project ``coderpad-cli``, owner
  ``adamtheturtle``, repository ``coderpad-cli``, workflow ``release.yml``,
  environment ``release``. Create that GitHub environment with appropriate
  protection before releasing. No PyPI token is stored in the repository.
* Enable GitHub Pages with the GitHub Actions source before manually running
  ``publish-site.yml``. CI builds documentation without deploying it.
* Allow Actions to create GitHub Releases and publish the repository's GHCR
  package. Make the GHCR package public after the first release if needed.
* No Homebrew tap, winget manifest, package-manager registration, Apple
  certificates, or TestPyPI configuration has been created. Do not advertise
  those installation paths until they exist.
* Configure branch protection and required checks after the first CI run.
  The public repository's tests and builds do not need a CoderPad key.
