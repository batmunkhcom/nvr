"""AI Engine Plugin Registry.

Plugins are loaded on startup and applied to each camera's FrameSampler
based on the camera's ``ai_plugins`` config field.

To add a new plugin:
    1. Create a module in this directory.
    2. Instantiate it in ``_initialize_plugins()``.
    3. The plugin will be automatically picked up by all cameras that
       list its ``name`` in their ``ai_plugins`` array.
"""

from __future__ import annotations

import structlog

from .base import AIPlugin

logger = structlog.get_logger()

_plugins: dict[str, AIPlugin] = {}


def _initialize_plugins() -> None:
    """Create one shared instance of each known plugin (lazy-safe)."""
    if _plugins:
        return

    from .lpr import LPRPlugin
    from .smart_alerts import SmartAlertsPlugin

    _plugins[LPRPlugin.name] = LPRPlugin()
    logger.info("plugin_loaded", name=LPRPlugin.name)

    _plugins[SmartAlertsPlugin.name] = SmartAlertsPlugin()
    logger.info("plugin_loaded", name=SmartAlertsPlugin.name)


def get_plugins_for_camera(ai_plugins: list[str] | None) -> list[AIPlugin]:
    """Return plugin instances the camera wants.

    Args:
        ai_plugins: List of plugin names from camera config (e.g. ["counter"]).
            None or empty list means no extra plugins.

    Returns:
        List of AIPlugin instances in load order.
    """
    _initialize_plugins()
    if not ai_plugins:
        return []
    result = []
    for name in ai_plugins:
        plugin = _plugins.get(name)
        if plugin is None:
            logger.warning("plugin_unknown", name=name)
            continue
        result.append(plugin)
    return result


async def start_all() -> None:
    """Start all registered plugins (called once at engine startup)."""
    _initialize_plugins()
    for name, plugin in _plugins.items():
        try:
            await plugin.start()
        except Exception:
            logger.warning("plugin_start_failed", name=name, exc_info=True)


async def stop_all() -> None:
    """Stop all registered plugins (called on shutdown)."""
    for name, plugin in _plugins.items():
        try:
            await plugin.stop()
        except Exception:
            logger.warning("plugin_stop_failed", name=name, exc_info=True)
