import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    username: str = "admin"
    password: str = ""
    history_limit: int = 50

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.environ.get("SEABIRDS_DATA_DIR", "data")).resolve(),
            username=os.environ.get("SEABIRDS_USERNAME", "admin"),
            password=os.environ.get("SEABIRDS_PASSWORD", ""),
            history_limit=max(1, min(1000, int(os.environ.get("SEABIRDS_HISTORY_LIMIT", "50")))),
        )
