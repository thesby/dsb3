"""Module acting as a singleton object for storing the configuration module.
"""

import importlib
import os

_CONFIG_DIR = "configurations"
DEFAULT = "default"
_config = None


def set_configuration(configuration):
    """Imports and initialises the configuration module."""
    global _config
    if configuration.endswith('.py'):
        configuration = configuration[:-3]
    if os.sep in configuration:
        configuration = os.path.relpath(configuration)
        configuration = configuration.replace(os.sep, '.')
        _config = importlib.import_module(configuration)
    else:
        _config = importlib.import_module("%s.%s" % (_CONFIG_DIR, configuration))
    if configuration != DEFAULT:
        print "loaded", _config

set_configuration(DEFAULT)

# dirty hack to access config attributes as if they were actually in the module
class Configuration():
    def __getattr__(self, name):
        return _config.__getattribute__(name)

config = Configuration()