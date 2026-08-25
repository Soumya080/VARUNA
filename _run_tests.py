import sys
import datetime as real_datetime

class FakeDatetimeModule:
    pass
fake_dt = FakeDatetimeModule()
for attr in dir(real_datetime):
    setattr(fake_dt, attr, getattr(real_datetime, attr))
setattr(fake_dt, 'UTC', real_datetime.timezone.utc)
sys.modules['datetime'] = fake_dt

import enum as real_enum
class FakeEnumModule:
    pass
fake_enum = FakeEnumModule()
for attr in dir(real_enum):
    setattr(fake_enum, attr, getattr(real_enum, attr))
class StrEnum(str, real_enum.Enum):
    pass
setattr(fake_enum, 'StrEnum', StrEnum)
sys.modules['enum'] = fake_enum

import pytest
sys.exit(pytest.main(['-q', 'tests/contract', 'tests/robustness']))
