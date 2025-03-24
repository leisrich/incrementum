# Custom hook for Pydantic to work around the 'compiled' attribute error
from PyInstaller.utils.hooks import collect_all

# Get all the normal stuff
datas, binaries, hiddenimports = collect_all('pydantic')

# Add these explicit imports that might be missed
hiddenimports.extend([
    'pydantic.json',
    'pydantic.dataclasses',
    'pydantic.schema',
    'pydantic.main',
    'pydantic.fields',
    'pydantic.error_wrappers',
    'pydantic.errors',
    'pydantic.utils',
    'pydantic.typing',
    'pydantic.validators',
    'pydantic.color',
    'pydantic.networks',
    'pydantic.datetime_parse',
    'pydantic.version',
    'pydantic.types'
])
