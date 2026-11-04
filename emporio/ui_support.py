"""Presentation helpers. No shared conversations, API calls or credentials in exports."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os
from dotenv import dotenv_values
from .backend import DEFAULT_MODEL
from .store import DATA
from .i18n import translate, LANGUAGES

CATEGORY_LABELS = {
    '1': 'Electric guitars', '2': 'Bass guitars', '3': 'Drums & percussion',
    '4': 'Keyboards & pianos', '5': 'Acoustic guitars', '6': 'Woodwind instruments',
    '7': 'Brass instruments', '8': 'Orchestral strings', '9': 'Ukuleles',
}


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default='', repr=False)
    model: str = DEFAULT_MODEL
    demo_customer_id: int | None = None


def load_settings(secrets=None, env=None, path=DATA.parent / '.env'):
    """Read server configuration without changing process-wide environment variables."""
    env = os.environ if env is None else env
    secrets = secrets or {}
    local = dotenv_values(Path(path)) if Path(path).is_file() else {}
    def read(name, default=''):
        return str(env.get(name) or secrets.get(name) or local.get(name) or default).strip()
    identity = read('EMPORIO_DEMO_CUSTOMER_ID')
    customer_id = int(identity) if identity.isdigit() and int(identity) > 0 else None
    return Settings(read('GROQ_API_KEY'), read('GROQ_MODEL', DEFAULT_MODEL), customer_id)


def transcript(records, mode, model, language='en'):
    t = lambda value: translate(value, language)
    lines = ['# Mel - Empório da Música', f"{t('Mode')}: {mode}", f"{t('Model setting')}: {model}",
             f"{t('Language')}: {LANGUAGES[language]}",
             f"{t('Exported (UTC)')}: {datetime.now(timezone.utc).isoformat()}",
             t('Offline mock is a scripted simulator, not a real model.') if mode == 'mock' else
             t('Real Groq model responses; source correctness still requires review.')]
    for record in records:
        lines.extend(['\n## ' + t('You') + '\n', record['question'], '\n## Mel\n', record['answer'],
                      t('Reply language: {language}').format(language=LANGUAGES[record.get('language', 'en')]),
                      '\n' + t('Sources') + ': ' + ', '.join(sorted({t(s['tool']) for s in record['trace']}))])
        if record['error']:
            lines.append(t('Response status') + ': ' + record['error'])
    return '\n'.join(lines) + '\n'
