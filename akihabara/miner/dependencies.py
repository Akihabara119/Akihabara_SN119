from functools import lru_cache
from akihabara.miner.config import MultimodalConfig


@lru_cache()
def get_multimodal_config() -> MultimodalConfig:
    return MultimodalConfig()