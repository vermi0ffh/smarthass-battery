"""Shared fixtures: the custom integration is loadable in every test."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """The integration lives in custom_components/: Home Assistant loads it only when this fixture is active."""
