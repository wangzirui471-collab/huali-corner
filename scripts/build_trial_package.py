"""Package application source only; never include runtime data or credentials."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = [
    'auth.py', 'community.py', 'db.py', 'manage_trial.py', 'market.py',
    'operations.py', 'publishing.py', 'seed.py', 'server.py', 'requirements.txt',
    'README.md', 'start-trial.bat', 'start-trial-8081.bat', 'render.yaml',
    '.python-version', '.gitignore',
]
SOURCE_DIRECTORIES = ['web', 'miniprogram', 'docs']


def build(output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / name for name in RUNTIME_FILES if (ROOT / name).is_file()]
    for directory in SOURCE_DIRECTORIES:
        files.extend(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and not path.is_symlink()
                     and not any(part.startswith('.') or part == '__pycache__' for part in path.relative_to(ROOT).parts)
                     and path.suffix.lower() not in {'.pyc', '.sqlite3', '.db', '.xlsx', '.zip'})
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(files):
            if path.is_symlink():
                raise ValueError('Refusing symlink: ' + str(path))
            archive.write(path, path.relative_to(ROOT).as_posix())
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(build(parser.parse_args().output))
