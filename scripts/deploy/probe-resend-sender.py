"""Probe the real Resend sender inside a deployed worker environment.

Runs the same sender the magic-link issue job uses and prints the exact
provider outcome so a blocked or misconfigured send surfaces in the
promote log instead of a generic provider_unavailable attempt failure.
"""

import os
from uuid import uuid4

from umbral.workers.composition import build_process_dependencies
from umbral.infrastructure.identity.registry import _resend_sender

# railway run merges the promote runner's environment with the service
# variables; drop the runner-only release/smoke inputs that Settings would
# reject as unknown, mirroring diagnose-preview-runtime.ps1.
for name in list(os.environ):
    if (
        name == "UMBRAL_MANIFEST_DATABASE_REVISION"
        or name == "UMBRAL_PREVIEW_BASE_URL"
        or name.startswith("UMBRAL_SMOKE_")
    ):
        del os.environ[name]

deps = build_process_dependencies()
sender = _resend_sender(deps.settings.resend_api_key)
result = sender(
    {
        "from": deps.settings.resend_from_email,
        "to": [f"probe-{uuid4().hex[:12]}@resend.dev"],
        "subject": "umbral sender probe",
        "text": "probe",
    },
    {},
)
print("sender probe OK:", result)
