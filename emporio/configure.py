"""Save a Groq key locally without displaying it or putting it in shell history."""
import getpass
import os
from .store import DATA
from .backend import DEFAULT_MODEL


def main():
    path = DATA.parent / '.env'
    if path.exists():
        raise SystemExit('A local .env already exists. Edit it locally; it will not be overwritten.')
    key = getpass.getpass('Groq API key (hidden; saved only in local ignored .env): ').strip()
    if not key or any(c in key for c in '\n\r\x00'):
        raise SystemExit('No valid key entered; no file written.')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(f'GROQ_API_KEY={key}\nGROQ_MODEL={DEFAULT_MODEL}\n')
    print('Key saved locally. Run python -m emporio --mode groq --trace. Keep the account on Free plan.')


if __name__ == '__main__':
    main()
