import sys
import enum
import datetime

# Monkeypatch for Python 3.10 support
if not hasattr(enum, "StrEnum"):
    class StrEnum(str, enum.Enum):
        pass
    enum.StrEnum = StrEnum

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc
