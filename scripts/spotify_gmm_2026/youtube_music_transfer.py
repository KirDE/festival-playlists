import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

from festival_playlists import (
    canonical_track_key,
    is_feat_track,
    should_skip_track_for_artist,
    simplify_name,
    token_overlap,
    track_version_penalty,
)

DEFAULT_CREDENTIALS = Path('/home/openclaw/.openclaw/credentials/youtube-music.json')
DEFAULT_OAUTH = Path('/home/openclaw/.openclaw/credentials/youtube-music-oauth.json')
DEFAULT_CACHE = Path('tmp/festival_playlists_cache/youtube_music_search_cache.json')
DEFAULT_OUTPUT_DIR = Path('outputs/youtube_music')
SEARCH_CACHE_VERSION = 'ytm-transfer-v2'
YOUTUBE_VERSION_HINTS = {
    'club',
    'demo',
    'dub',
    'english',
    'medieval techno',
    'mix',
    'rework',
    'sample',
}


def parse_report_tracks(report: dict) -> list[dict]:
    tracks = []
    seen = set()
    for entry in report.get('report', []):
        lineup_artist = entry.get('artist') or entry.get('query_artist') or ''
        query_artist = entry.get('query_artist') or lineup_artist
        for label in entry.get('tracks', []):
            if ' - ' not in label:
                continue
            artist, title = label.split(' - ', 1)
            key = (simplify_name(artist), canonical_track_key(title))
            if key in seen:
                continue
            seen.add(key)
            tracks.append({
                'lineup_artist': lineup_artist,
                'query_artist': query_artist,
                'artist': artist,
                'title': title,
                'label': label,
            })
    return tracks


def youtube_candidate_to_track(candidate: dict) -> dict:
    return {
        'name': candidate.get('title') or '',
        'artists': [{'name': artist.get('name') or ''} for artist in candidate.get('artists', [])],
        'duration_ms': int(candidate.get('duration_seconds') or 0) * 1000,
    }


def version_hint_text(text: str) -> str:
    lowered = unicodedata.normalize('NFKD', text.lower()).encode('ascii', 'ignore').decode('ascii')
    lowered = re.sub(r'[^a-z0-9]+', ' ', lowered)
    return ' '.join(lowered.split())


def youtube_version_penalty(query_title: str, candidate_title: str) -> int:
    query_key = version_hint_text(query_title)
    title_key = version_hint_text(candidate_title)
    return sum(1 for hint in YOUTUBE_VERSION_HINTS if hint in title_key and hint not in query_key)


def youtube_candidate_score(query: dict, candidate: dict) -> tuple | None:
    video_id = candidate.get('videoId')
    if not video_id:
        return None

    track = youtube_candidate_to_track(candidate)
    skip_reason = should_skip_track_for_artist(query['query_artist'], track, query['lineup_artist'])
    if skip_reason:
        return None
    if youtube_version_penalty(query['title'], candidate.get('title') or '') > 0:
        return None

    artist_names = [artist['name'] for artist in track.get('artists', []) if artist.get('name')]
    artist_score = max(token_overlap(query['artist'], artist) for artist in artist_names) if artist_names else 0.0
    if simplify_name(query['artist']) in [simplify_name(artist) for artist in artist_names]:
        artist_score += 1.0

    target_key = canonical_track_key(query['title'])
    title_key = canonical_track_key(candidate.get('title') or '')
    title_score = 1.0 if title_key == target_key else token_overlap(query['title'], candidate.get('title') or '')
    if title_score < 0.45:
        return None

    return (
        artist_score,
        title_score,
        candidate.get('resultType') == 'song',
        not is_feat_track(track),
        -track_version_penalty(track),
        int(candidate.get('duration_seconds') or 0),
    )


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_ytmusic(auth_path: Path | None = None, credentials_path: Path = DEFAULT_CREDENTIALS):
    from ytmusicapi import YTMusic
    from ytmusicapi.auth.oauth.credentials import OAuthCredentials

    if auth_path and auth_path.exists():
        creds = load_json(credentials_path, {})
        oauth_credentials = OAuthCredentials(creds['client_id'], creds['client_secret'])
        return YTMusic(auth=str(auth_path), oauth_credentials=oauth_credentials)
    return YTMusic()


def search_youtube_track(ytmusic, query: dict, cache: dict, *, pause_seconds: float = 0.0) -> dict | None:
    cache_key = f"{SEARCH_CACHE_VERSION}:{query['artist']} - {query['title']}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None

    results = []
    for search_filter in ('songs', 'videos'):
        try:
            results.extend(ytmusic.search(f"{query['artist']} {query['title']}", filter=search_filter, limit=10))
        except Exception as exc:
            cache[cache_key] = {'error': f'{type(exc).__name__}: {exc}'}
            return None
        if results:
            break

    best = None
    best_score = None
    seen_video_ids = set()
    for candidate in results:
        video_id = candidate.get('videoId')
        if not video_id or video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)
        score = youtube_candidate_score(query, candidate)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best = candidate

    cache[cache_key] = best or {}
    if pause_seconds:
        time.sleep(pause_seconds)
    return best


def replace_playlist_items(ytmusic, playlist_id: str, video_ids: list[str]) -> None:
    current = ytmusic.get_playlist(playlist_id, limit=None).get('tracks', [])
    removable = [
        {'videoId': item.get('videoId'), 'setVideoId': item.get('setVideoId')}
        for item in current
        if item.get('videoId') and item.get('setVideoId')
    ]
    for idx in range(0, len(removable), 100):
        ytmusic.remove_playlist_items(playlist_id, removable[idx:idx + 100])
    for idx in range(0, len(video_ids), 100):
        ytmusic.add_playlist_items(playlist_id, video_ids[idx:idx + 100], duplicates=False)


def publish_playlist(ytmusic, source_report: dict, video_ids: list[str], playlist_id: str | None) -> tuple[str, str]:
    title = source_report['playlist_name']
    description = 'Listen to all bands from Summer Breeze 2026.'
    if playlist_id:
        ytmusic.edit_playlist(playlist_id, title=title, description=description, privacyStatus='PUBLIC')
        replace_playlist_items(ytmusic, playlist_id, video_ids)
    else:
        playlist_id = ytmusic.create_playlist(title, description, privacy_status='PUBLIC', video_ids=video_ids[:100])
        for idx in range(100, len(video_ids), 100):
            ytmusic.add_playlist_items(playlist_id, video_ids[idx:idx + 100], duplicates=False)
    return playlist_id, f'https://music.youtube.com/playlist?list={playlist_id}'


def build_youtube_report(source_report: dict, source_tracks: list[dict], matched: list[dict], missing: list[dict], playlist_id: str = '', playlist_url: str = '') -> dict:
    seen_video_ids = set()
    duplicate_video_ids = []
    seen_song_keys = set()
    duplicate_song_keys = []
    for item in matched:
        video_id = item['videoId']
        if video_id in seen_video_ids:
            duplicate_video_ids.append(video_id)
        seen_video_ids.add(video_id)
        song_key = canonical_track_key(item['title'])
        if song_key in seen_song_keys:
            duplicate_song_keys.append(item['label'])
        seen_song_keys.add(song_key)

    return {
        'festival': source_report.get('festival'),
        'playlist_name': source_report.get('playlist_name'),
        'source_playlist_url': source_report.get('playlist_url'),
        'playlist_id': playlist_id,
        'playlist_url': playlist_url,
        'source_track_count': len(source_tracks),
        'matched_track_count': len(matched),
        'missing_track_count': len(missing),
        'duplicate_video_ids': duplicate_video_ids,
        'duplicate_song_keys': duplicate_song_keys,
        'matched': matched,
        'missing': missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Transfer a festival playlist report to YouTube Music.')
    parser.add_argument('--report', default='outputs/festival_playlists/summer_breeze_2026.json')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT_DIR / 'summer_breeze_2026.json'))
    parser.add_argument('--cache', default=str(DEFAULT_CACHE))
    parser.add_argument('--credentials', default=str(DEFAULT_CREDENTIALS))
    parser.add_argument('--oauth', default=str(DEFAULT_OAUTH))
    parser.add_argument('--playlist-id', default=os.environ.get('YOUTUBE_MUSIC_PLAYLIST_ID', ''))
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--pause-seconds', type=float, default=0.0)
    args = parser.parse_args()

    report_path = Path(args.report)
    source_report = load_json(report_path, {})
    source_tracks = parse_report_tracks(source_report)
    if not source_tracks:
        raise RuntimeError(f'no tracks found in report: {report_path}')

    ytmusic = load_ytmusic(Path(args.oauth) if args.publish else None, Path(args.credentials))
    cache_path = Path(args.cache)
    cache = load_json(cache_path, {})
    matched = []
    missing = []
    used_video_ids = set()

    for index, query in enumerate(source_tracks, 1):
        candidate = search_youtube_track(ytmusic, query, cache, pause_seconds=args.pause_seconds)
        if not candidate:
            missing.append(query)
            print(f"[{index}/{len(source_tracks)}] missing: {query['label']}")
            continue
        video_id = candidate['videoId']
        if video_id in used_video_ids:
            missing.append({**query, 'reason': 'duplicate_video_id', 'videoId': video_id})
            print(f"[{index}/{len(source_tracks)}] duplicate video: {query['label']}")
            continue
        used_video_ids.add(video_id)
        matched.append({
            **query,
            'youtube_title': candidate.get('title'),
            'youtube_artists': [artist.get('name') for artist in candidate.get('artists', [])],
            'duration_seconds': candidate.get('duration_seconds'),
            'videoId': video_id,
            'youtube_url': f'https://music.youtube.com/watch?v={video_id}',
        })
        print(f"[{index}/{len(source_tracks)}] matched: {query['label']} -> {candidate.get('title')}")
        if index % 25 == 0:
            save_json(cache_path, cache)

    save_json(cache_path, cache)

    playlist_id = ''
    playlist_url = ''
    if args.publish:
        playlist_id, playlist_url = publish_playlist(
            ytmusic,
            source_report,
            [item['videoId'] for item in matched],
            args.playlist_id or None,
        )

    output = build_youtube_report(source_report, source_tracks, matched, missing, playlist_id, playlist_url)
    save_json(Path(args.output), output)
    print(json.dumps({
        'output': args.output,
        'playlist_url': playlist_url,
        'source_track_count': output['source_track_count'],
        'matched_track_count': output['matched_track_count'],
        'missing_track_count': output['missing_track_count'],
        'duplicate_video_ids': len(output['duplicate_video_ids']),
        'duplicate_song_keys': len(output['duplicate_song_keys']),
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
