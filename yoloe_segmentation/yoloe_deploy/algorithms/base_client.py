"""base client wrapper. All fastapi client in algorithm module should inherit from BaseClient class.

Authors: wuyidong
Create Date: 2025-11-20
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional

import yaml


class BaseClient(ABC):
    @abstractmethod
    def __init__(
        self, config: Optional[Dict] = None, config_path: Optional[str] = None
    ):
        """Initialize client with config file and/or config dict.

        Args:
            config_path: Path to YAML config file
            config: Configuration dictionary that overrides config_path settings
        """
        self.config = {}
        self.config_path = config_path

        # Load config from file if provided
        if config_path is not None:
            try:
                with open(config_path, "r") as f:
                    self.config = yaml.safe_load(f)
                print(f"Loaded config from {config_path}")
                print(yaml.dump(self.config, default_flow_style=False))
            except Exception as e:
                raise ValueError(f"Failed to load config file {config_path}: {e}")

        # Override with config dict if provided
        if config is not None:
            print("Overriding with provided config:")
            print(yaml.dump(config, default_flow_style=False))
            self.config.update(config)
            print("Final config:")
            print(yaml.dump(self.config, default_flow_style=False))

        if not self.config:
            raise ValueError("Either config_path or config must be provided")

    @abstractmethod
    def predict(self, **kwargs):
        pass
