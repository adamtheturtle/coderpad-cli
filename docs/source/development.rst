Development and releases
========================

This repository follows the current main branch of ``literalizer-cli``
(inspected at ``cf435b8ee67dd9900d795a8438622ad02aaaf730``).
It adapts its src layout, Click entry points, setuptools-scm versions, uv
lockfile, strict checks, branch coverage, Sphinx, Towncrier, and distribution
builds.
It does not inherit conversion features, historical release notes, checker
exceptions, Homebrew or winget publication, signing secrets, or unavailable
artifact links.
The SDK baseline is the released ``coderpad-py==2026.10.1.1`` in ``uv.lock``.

.. code-block:: shell

   git submodule update --init spec
   uv sync --locked --group dev
   uv run pytest
   uv run prek run --all-files
   uv run prek run --all-files --stage pre-push
   uv run sphinx-build -W --keep-going -b html docs/source docs/build/html
   uv build
   uv run twine check dist/*
   uv run check-wheel-contents dist/*.whl

Tests use the real SDK with its public ``Transport`` interface.
Tests run offline through the SDK transport boundary.
Retry behavior remains the SDK's responsibility.
Synthetic transports assert the exact mutation payload, including the absence
of title, description, language, solution, and instruction fields.
Additional contract tests exercise the SDK's default HTTPX transport through
RESPX.
They validate form, multipart, and variant JSON fields against the pinned
shared OpenAPI specification in ``spec/openapi.json``.
They also inspect the SDK-generated ZIP bytes and verify that metadata is
absent from the outgoing update.
The mock rejects every unregistered request.
No SDK methods are replaced.
See ``tests/fixtures/README.rst`` for the fixture's source and update policy.

The specification is owned by ``adamtheturtle/coderpad-openapi``.
The ``spec`` Git submodule pins an immutable commit from that repository.
Repeat ``git submodule update --init spec`` after pulling a pin update.
Tests only read the local document and never download it.
Installed CLI commands do not depend on the submodule.

Add a Towncrier feature or bugfix fragment for each user-visible change.

Versions derive from Git tags using setuptools-scm.
Untagged initial builds have a development version.
Use date-based tags such as ``2026.10.02`` for releases; no release tag is
created as part of repository initialization.
Before tagging a release, assemble notes with
``uv run towncrier build --yes --version VERSION``, commit the changelog, then
write the same version to ``VERSION``, commit it, then tag the commit.
Pushing a tag is the explicit publication trigger.
The release workflow builds and checks packages, builds three standalone
binaries, and then publishes to PyPI, GitHub Releases, and GHCR.

Towncrier assembles reStructuredText for the Sphinx changelog.
The release workflow uses Pandoc to convert only the tagged version's section
to GitHub Markdown before publishing.
Missing or duplicate version sections fail validation.
Pull requests check the same rendering path using ``VERSION``.
Install Pandoc locally (``brew install pandoc`` on macOS) to preview the notes:

.. code-block:: shell

   RELEASE_VERSION="$(cat VERSION)"
   export RELEASE_VERSION
   pandoc --from=rst --to=gfm --wrap=none --fail-if-warnings --lua-filter=bin/release_notes.lua CHANGELOG.rst --output=release-notes.md

Check the rendered Markdown before pushing a release tag.

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

The Docker image builds a wheel from this checkout rather than depending on an
unpublished PyPI artifact.
Mount content read-only and forward the existing environment variable for an
upload:

.. code-block:: shell

   docker run --rm -e CODERPAD_API_KEY -v "$PWD/starter:/starter:ro" coderpad-cli questions upload 123456 --directory /starter --dry-run

The Nix flake uses uv2nix and the committed lockfiles.
Its build injects an SCM version because Git metadata is unavailable in Nix
source snapshots.
The standalone-binary workflow runs for releases and manual builds.
Unsigned macOS builds use PyInstaller's ad-hoc signature.
Distribution signing and notarization are required by the release workflow.
See :doc:`macos-releases` for signing, notarization, and credential setup.

External setup
--------------

* Register a PyPI trusted publisher for project ``coderpad-cli``, owner
  ``adamtheturtle``, repository ``coderpad-cli``, workflow ``release.yml``,
  environment ``release``.
  Create that GitHub environment with appropriate protection before releasing.
  No PyPI token is stored in the repository.
* Enable GitHub Pages with the GitHub Actions source before manually running
  ``publish-site.yml``.
  CI builds documentation without deploying it.
* Allow Actions to create GitHub Releases and publish the repository's GHCR
  package.
  Make the GHCR package public after the first release if needed.
* Configure the five macOS signing and notarization repository secrets in
  :doc:`macos-releases` before releasing.
  A missing credential fails the build; releases cannot fall back to an
  unsigned macOS binary.
* No Homebrew tap, winget manifest, package-manager registration, or TestPyPI
  configuration has been created.
  Do not advertise those installation paths until they exist.

The default branch requires 16 Actions checks: tests on Python 3.12, 3.13, and
3.14 across Linux, macOS, and Windows, lint on Linux and Windows,
documentation, packaging, two Nix builds, and automatic fixes.
The public repository's tests and builds do not need a CoderPad key.

Quality checks
--------------

The quality configuration follows Literalizer at commit
``30b54d2199171429ba44baa61467df14bcf87a68``.
Run the fast checks before committing and the type checks before pushing.
Pylint and documentation builders also run in CI.
Install the Enchant library and the US English dictionary for spelling checks
(``brew install enchant`` on macOS).

.. code-block:: shell

   uv run --locked prek run --all-files --stage pre-commit
   uv run --locked prek run --all-files --stage pre-push
   uv run --locked prek run --all-files --stage manual --group pylint
   uv run --locked prek run --all-files --stage manual --group docs

Checks cover dependency declarations, dead code, package metadata, docstrings,
keyword-only parameters, documentation examples, shell commands, and Actions
security alongside the four strict type checkers and branch coverage.
Generated version files are excluded from source checks.
The SDK owns its HTTP client and models.

Literalizer CLI check parity
----------------------------

Additional checks follow ``literalizer-cli`` at commit
``cf435b8ee67dd9900d795a8438622ad02aaaf730``.
The dedicated ``uv-lock`` hook checks that dependency metadata and the lockfile
agree.
All Python source files are checked, including documentation and binary
wrappers.
Tests run in parallel and check runtime types in the public package, tests, and
fixtures.
Help text for every command is compared with committed regression snapshots.
Review any help change before updating snapshots:

.. code-block:: shell

   uv run --locked pytest tests/test_help.py --regen-all --no-cov

CI runs all hook stages on Linux and Windows and runs daily on ``main``.
The existing stricter lint, documentation, and workflow security checks remain
enabled.
