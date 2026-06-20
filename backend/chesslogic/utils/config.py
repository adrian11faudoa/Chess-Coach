"""
Configuration for ChessCoach Web.
Reads from environment variables (AWS / Docker) with sensible defaults.
"""

import os
from pathlib import Path
from typing import Any


class Config:
    DEFAULTS = {
        "stockfish_path": "",
        "engine_elo": 1500,
        "engine_depth": 20,
        "engine_threads": 2,
        "engine_hash_mb": 256,
        "db_path": "",
        "coach_verbosity": "normal",
        "theme": "dark",
        "show_engine_arrow": True,
        "analysis_depth": 18,
        "analysis_multipv": 3,
        "auto_analyze_game": True,
        "show_opening_info": True,
        "time_control": "10+0",
    }

    ENV_MAP = {
        "STOCKFISH_PATH": "stockfish_path",
        "DB_PATH":        "db_path",
        "ENGINE_ELO":     "engine_elo",
        "ENGINE_THREADS": "engine_threads",
        "ENGINE_HASH_MB": "engine_hash_mb",
    }

    def __init__(self):
        self._data = dict(self.DEFAULTS)
        for env_key, cfg_key in self.ENV_MAP.items():
            val = os.environ.get(env_key)
            if val is not None:
                default = self.DEFAULTS.get(cfg_key)
                if isinstance(default, int):
                    try: val = int(val)
                    except ValueError: pass
                self._data[cfg_key] = val

        if not self._data["db_path"]:
            data_dir = os.environ.get("DATA_DIR", str(Path.home() / ".chesscoach"))
            os.makedirs(data_dir, exist_ok=True)
            self._data["db_path"] = os.path.join(data_dir, "chesscoach.db")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"Config has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_") or name not in self.DEFAULTS:
            super().__setattr__(name, value)
        else:
            self._data[name] = value
