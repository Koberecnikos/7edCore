import os

__version__ = os.environ.get("SEVENEDCORE_VERSION", "dev").lstrip("v")
