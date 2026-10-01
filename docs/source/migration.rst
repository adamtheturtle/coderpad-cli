Migrating a repository uploader
===============================

Keep question IDs, source-path mappings, builds, and upload-on-push workflows
in the consuming repository. The public CLI deliberately knows none of them.
The existing interview checkout is not modified by this implementation.

After publishing the CLI, add a released ``coderpad-cli`` version to the
consumer's development dependencies. Replace each shell invocation with:

.. code-block:: shell

   uv run --extra=dev coderpad questions upload 123456 --directory starter/python --exclude '*.zip'
   uv run --extra=dev coderpad questions upload 234567 --file "$prepared_snippet"

Keep ``set -euo pipefail``, changing to the repository root, and the existing
question/path mapping in the shell script. Keep builds and the upload-on-push
workflow in that repository, including its secret and dependency group.
The workflow continues calling the shell script after the required builds.

The old snippet operation strips documentation slice markers, trims outer
whitespace, and appends a newline. The public ``--file`` option preserves text
exactly. Move the old snippet transformation into a consumer-owned preparation
step that writes a temporary UTF-8 file. Upload that prepared file and remove
it afterward with a shell trap. Keep the marker list and all interview text
in the consumer. Test the preparation step separately; neither markers nor
source code belong in this public package.

Before enabling mutations, run every replacement command with ``--dry-run``
and compare its selection with the existing uploader. Retain explicit ZIP
exclusion to preserve the existing directory behavior. Resolve any selected
symlinks in the consumer rather than copying their targets implicitly.
