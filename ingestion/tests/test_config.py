import pytest

from haze_ingest.config import ConfigError, Settings


def test_from_env_reads_both_vars():
    s = Settings.from_env({"FIRMS_MAP_KEY": "k", "GCP_PROJECT_ID": "p"})
    assert s == Settings(firms_map_key="k", gcp_project_id="p")


@pytest.mark.parametrize("missing", ["FIRMS_MAP_KEY", "GCP_PROJECT_ID"])
def test_from_env_names_missing_var(missing):
    env = {"FIRMS_MAP_KEY": "k", "GCP_PROJECT_ID": "p"}
    env[missing] = "  "
    with pytest.raises(ConfigError, match=missing):
        Settings.from_env(env)


def test_config_error_never_echoes_values():
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({"FIRMS_MAP_KEY": "secret123"})
    assert "secret123" not in str(exc.value)
