"""
Custom static-file storage backend for ARMGUARD RDS.

Subclasses WhiteNoise's CompressedManifestStaticFilesStorage to prevent
URL-rewriting (post-processing) on .mjs files.  PDF.js bundles
(pdf.min.mjs, pdf.worker.min.mjs) are large minified files that must not
be scanned for internal URL substitutions — doing so corrupts them.
All other static files behave normally (hashed, compressed, URL-rewritten).
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ArmguardStaticStorage(CompressedManifestStaticFilesStorage):
    """Skip URL-rewriting (but not hashing/copying/compression) for .mjs files."""

    # Degrade gracefully when a file is absent from the manifest (e.g. stale
    # manifest after a deploy that did not finish collectstatic) instead of
    # raising ValueError and serving a 500 page.
    manifest_strict = False

    def matches_patterns(self, path, patterns=None):
        # .mjs files must not be scanned for internal URL substitutions —
        # they are large minified bundles and the rewriter would corrupt them.
        if path.endswith('.mjs'):
            return False
        return super().matches_patterns(path, patterns)
