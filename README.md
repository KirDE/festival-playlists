# Festival Playlists

Scripts for building Spotify playlists for metal festivals from festival lineups, recent setlist.fm songs, and Spotify popularity.

## Main scripts

- `scripts/spotify_gmm_2026/festival_playlists.py` - current playlist builder for Graspop, Wacken, Rock im Park, Summer Breeze, and Impericon.
- `scripts/spotify_gmm_2026/spotify_auth.py` - Spotify OAuth token loading and refresh.
- `scripts/spotify_gmm_2026/init_spotify_auth.py` - exchanges a Spotify callback `code` for local tokens or refreshes the token file.

## Setup

Copy `.env.example` to `.env` and fill the required values:

```bash
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SETLIST_API_KEY=...
```

Then export the variables before running the scripts.

Spotify tokens are stored locally in `tmp/spotify_tokens.json` by default and are intentionally ignored by git.

## Auth

Use a Spotify authorization URL with the scopes:

```text
playlist-modify-public playlist-modify-private
```

After approving access, pass the callback `code` to:

```bash
python3 scripts/spotify_gmm_2026/init_spotify_auth.py "<code>"
```

## Build playlists

```bash
python3 scripts/spotify_gmm_2026/festival_playlists.py
```

Reports are written to `outputs/festival_playlists/`.
