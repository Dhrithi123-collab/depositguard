import pathlib
# Extend this package's __path__ to include the actual backend app directory
# The backend/app folder is a sibling of this shim's parent directory
__path__.append(str(pathlib.Path(__file__).parent.parent / 'backend' / 'app'))
