Migrating a repository uploader
===============================

Keep question IDs, source-path mappings, builds, and upload-on-push workflows
in the consuming repository.
The public CLI deliberately knows none of them.
The existing interview checkout is not modified by this change.

After publishing the CLI, add a released ``coderpad-cli`` version to the
consumer's development dependencies.
Replace each shell invocation with:

.. code-block:: shell

   uv run --extra=dev coderpad questions upload 123456 --directory starter/python --exclude '*.zip'
   prepared_snippet=$(mktemp)
   # Run the consumer's preparation step to populate this file.
   uv run --extra=dev coderpad questions upload 234567 --file "$prepared_snippet"
   rm -- "$prepared_snippet"

Keep ``set -euo pipefail``, changing to the repository root, and the existing
question/path mapping in the shell script.
Keep builds and the upload-on-push workflow in that repository, including its
secret and dependency group.
The workflow continues calling the shell script after the required builds.

For existing question variants, add ``--variant-id VARIANT_ID`` to the upload
command.
Keep variant IDs and their source paths in the consumer's shell script too.
Use ``--dry-run`` to validate UTF-8 project files before enabling variant
uploads.

The old snippet operation removes documentation slice markers.
It also trims outer whitespace and appends a newline.
The public ``--file`` option preserves text exactly.
Move the old snippet transformation into a consumer-owned preparation step that
writes a temporary UTF-8 file.
Upload that prepared file and remove it afterward with a shell trap.
Keep the marker list and all interview text in the consumer.
Test the preparation step separately in the consumer.

Before enabling mutations, run every replacement command with ``--dry-run`` and
compare its selection with the existing uploader.
Retain explicit ZIP exclusion to preserve the existing directory behavior.
Resolve any selected symlinks in the consumer rather than copying their targets
implicitly.
