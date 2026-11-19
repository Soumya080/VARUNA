import sys
import datetime as real_datetime

# Monkeypatch datetime to include UTC for Python 3.10 compatibility
class FakeDatetimeModule:
    pass
    
fake_dt = FakeDatetimeModule()
for attr in dir(real_datetime):
    setattr(fake_dt, attr, getattr(real_datetime, attr))
    
setattr(fake_dt, "UTC", real_datetime.timezone.utc)
# pyrefly: ignore [unsupported-operation]
sys.modules['datetime'] = fake_dt

import enum as real_enum
class FakeEnumModule:
    pass

fake_enum = FakeEnumModule()
for attr in dir(real_enum):
    setattr(fake_enum, attr, getattr(real_enum, attr))
    
# Basic polyfill for StrEnum
class StrEnum(str, real_enum.Enum):
    pass
    
setattr(fake_enum, "StrEnum", StrEnum)
sys.modules['enum'] = fake_enum

# Now we can safely import the contracts without Python 3.10 crashing on `from datetime import UTC`
from experiments.go_nogo_v2.sweep import run_sweep

if __name__ == "__main__":
    run_sweep()
