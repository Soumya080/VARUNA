import os
import glob

def fix_utc(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Replace 'from datetime import UTC, datetime' with 'from datetime import timezone, datetime'
    content = content.replace('from datetime import UTC, datetime', 'from datetime import timezone, datetime')
    
    # Replace 'datetime.now(UTC)' with 'datetime.now(timezone.utc)'
    content = content.replace('datetime.now(UTC)', 'datetime.now(timezone.utc)')
    
    # Replace '.astimezone(UTC)' with '.astimezone(timezone.utc)'
    content = content.replace('.astimezone(UTC)', '.astimezone(timezone.utc)')
    
    # Optional: If there are bare 'UTC' left that aren't in docstrings, replace them but we can just use regex for safe replacements.
    # Actually, replacing all exact matches of 'UTC' as a python token is safer but let's stick to known cases
    
    with open(filepath, 'w') as f:
        f.write(content)

for filepath in glob.glob('packages/varuna_contracts/*.py'):
    fix_utc(filepath)

