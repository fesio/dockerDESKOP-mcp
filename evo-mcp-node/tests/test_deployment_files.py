from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.skipif(
    not (ROOT / ".github").exists(), reason="repository-level deployment files are outside image context"
)


def test_default_compose_has_no_docker_socket():
    compose = (ROOT / "evo-mcp-node" / "compose.yaml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in compose


def test_wif_is_scoped_to_production_environment():
    script = (ROOT / "evo-mcp-node" / "scripts" / "setup-gcp-wif.ps1").read_text(
        encoding="utf-8"
    )
    assert "attribute.environment=assertion.environment" in script
    assert "assertion.environment=='production'" in script


def test_cloud_run_uses_dedicated_runtime_service_account():
    workflow = (ROOT / ".github" / "workflows" / "evo-mcp-cloudrun.yml").read_text(
        encoding="utf-8"
    )
    assert "--service-account" in workflow
    assert "evo-mcp-runtime@" in workflow
