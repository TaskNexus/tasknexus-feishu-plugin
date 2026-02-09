"""
TaskNexus Feishu Plugin

Provides Feishu (飞书) messaging channel integration for TaskNexus.
"""

from .channel import FeishuChannel

__version__ = "0.1.0"


def register(manager):
    """
    Plugin registration entry point.
    
    Called by TaskNexus PluginManager during plugin discovery.
    
    Args:
        manager: PluginManager instance
    """
    manager.register_channel(FeishuChannel())


__all__ = ['register', 'FeishuChannel']
