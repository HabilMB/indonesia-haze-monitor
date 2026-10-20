import os
from dataclasses import dataclass, field
from typing import Mapping


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    firms_map_key: str = field(repr=False)
    gcp_project_id: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        names = {"firms_map_key": "FIRMS_MAP_KEY", "gcp_project_id": "GCP_PROJECT_ID"}
        values = {field: env.get(var, "").strip() for field, var in names.items()}
        missing = [names[field] for field, value in values.items() if not value]
        if missing:
            raise ConfigError(f"Missing required env var(s): {', '.join(missing)}. See .env.example.")
        return cls(**values)
