"""Pytest configuration for detective tests."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-llm", action="store_true", default=False,
        help="Run tests that call an LLM via the Copilot SDK (slow, requires auth)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-llm"):
        skip_llm = pytest.mark.skip(reason="Need --run-llm to run LLM tests")
        for item in items:
            if "llm" in item.keywords:
                item.add_marker(skip_llm)
