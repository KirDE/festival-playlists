import argparse
import json
from pathlib import Path

from ytmusicapi import setup_oauth

DEFAULT_CREDENTIALS = Path('/home/openclaw/.openclaw/credentials/youtube-music.json')
DEFAULT_OAUTH = Path('/home/openclaw/.openclaw/credentials/youtube-music-oauth.json')


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a YouTube Music OAuth token with device-flow auth.')
    parser.add_argument('--credentials', default=str(DEFAULT_CREDENTIALS))
    parser.add_argument('--oauth', default=str(DEFAULT_OAUTH))
    args = parser.parse_args()

    credentials_path = Path(args.credentials)
    oauth_path = Path(args.oauth)
    credentials = json.loads(credentials_path.read_text(encoding='utf-8'))
    oauth_path.parent.mkdir(parents=True, exist_ok=True)
    setup_oauth(
        credentials['client_id'],
        credentials['client_secret'],
        filepath=str(oauth_path),
        open_browser=False,
    )
    oauth_path.chmod(0o600)
    print(f'Saved YouTube Music OAuth token to {oauth_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
