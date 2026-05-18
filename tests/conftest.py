"""Test-suite hermeticity guards.

Globally disables network-dependent tiers (LLM situation assessment, etc.)
so the unit-test suite stays deterministic and offline-safe regardless of
the developer's local OPENAI_API_KEY. Individual tests that exercise the
LLM tier MUST mock its entry points explicitly.
"""

import os


def _set_env_defaults() -> None:
    # Never call the premium-LLM situation assessor during tests; the
    # deterministic chain + main router are the contract we pin.
    os.environ.setdefault("ASSESSMENT_LLM_ENABLED", "0")


_set_env_defaults()
