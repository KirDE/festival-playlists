import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('SETLIST_API_KEY', 'test')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'spotify_gmm_2026'))

import festival_playlists as playlists


def make_track(name='Song', artists=None, duration_ms=180_000):
    return {
        'name': name,
        'artists': [{'name': artist} for artist in (artists or ['Example Artist'])],
        'duration_ms': duration_ms,
    }


class TrackFilterTest(unittest.TestCase):
    def test_skips_tracks_where_lineup_artist_is_only_featured(self):
        track = make_track(artists=['Kontra K', 'Anna Grey'])

        self.assertEqual(playlists.should_skip_track_for_artist('Anna Grey', track), 'primary_artist_mismatch')

    def test_skips_tracks_where_lineup_artist_is_secondary_collaborator(self):
        track = make_track(name='RATATATA', artists=['BABYMETAL', 'Electric Callboy'])

        self.assertEqual(playlists.should_skip_track_for_artist('Electric Callboy', track), 'primary_artist_mismatch')

    def test_accepts_primary_artist_match_with_featured_guests(self):
        track = make_track(artists=['Anna Grey', 'Kontra K'])

        self.assertIsNone(playlists.should_skip_track_for_artist('Anna Grey', track))

    def test_accepts_alias_primary_artist_match(self):
        track = make_track(artists=['Cavalera Conspiracy'])

        self.assertIsNone(playlists.should_skip_track_for_artist('Cavalera', track))

    def test_skips_single_token_artist_as_secondary_primary_token(self):
        track = make_track(artists=['Sub Focus'])

        self.assertEqual(playlists.should_skip_track_for_artist('Focus.', track), 'primary_artist_mismatch')

    def test_rock_im_park_uses_2026_snapshot_when_live_page_has_no_lineup(self):
        class Response:
            text = '<html><title>Rock im Park 2027</title></html>'

        with patch.object(playlists.requests, 'get', return_value=Response()):
            artists, headliners = playlists.fetch_rock_im_park()

        self.assertIn('Electric Callboy', artists)
        self.assertEqual(headliners, playlists.ROCK_IM_PARK_2026_HEADLINERS)

    def test_refuses_to_overwrite_existing_playlist_with_empty_lineup(self):
        festival = playlists.Festival(
            key='empty_test',
            display_name='Empty Test',
            playlist_name='Empty Test',
            description='Empty Test',
            lineup_fn=lambda: ([], []),
            existing_playlist_id='playlist-id',
        )

        with self.assertRaisesRegex(RuntimeError, 'lineup is empty'):
            playlists.build_playlist(festival, 'user-id')

    def test_spotify_search_prefers_clean_version_over_feat_version(self):
        clean = make_track(name='Festival Song', artists=['Example Artist'])
        clean.update({'uri': 'spotify:track:clean', 'popularity': 50})
        feat = make_track(name='Festival Song (feat. Guest)', artists=['Example Artist', 'Guest'])
        feat.update({'uri': 'spotify:track:feat', 'popularity': 90})

        with patch.object(playlists, 'spotify_get', return_value={'tracks': {'items': [feat, clean]}}):
            result = playlists.spotify_search_track('Example Artist', 'Festival Song')

        self.assertEqual(result['uri'], 'spotify:track:clean')

    def test_spotify_top_tracks_prefers_clean_versions_before_feat_versions(self):
        artist = {'id': 'artist-id', 'name': 'Example Artist', 'followers': {'total': 1}}
        clean = make_track(name='Clean Song', artists=['Example Artist'])
        clean.update({'uri': 'spotify:track:clean', 'popularity': 50})
        feat = make_track(name='Featured Song (feat. Guest)', artists=['Example Artist', 'Guest'])
        feat.update({'uri': 'spotify:track:feat', 'popularity': 90})

        with patch.object(playlists, 'spotify_get_artist_by_id', return_value=artist), \
                patch.object(playlists, 'spotify_get', return_value={'tracks': [feat, clean]}):
            _, tracks = playlists.spotify_top_tracks('Example Artist', limit=2, artist_id='artist-id')

        self.assertEqual([track['uri'] for track in tracks], ['spotify:track:clean', 'spotify:track:feat'])

    def test_live_word_inside_song_title_is_not_live_version(self):
        track = make_track(name='Live It Up', artists=['Example Artist'])

        self.assertEqual(playlists.track_version_penalty(track), 0)
        self.assertIsNone(playlists.should_skip_track_for_artist('Example Artist', track))

    def test_live_version_marker_is_penalized(self):
        track = make_track(name='Clean Song - Live at Wacken', artists=['Example Artist'])

        self.assertEqual(playlists.track_version_penalty(track), 2)
        self.assertEqual(playlists.should_skip_track_for_artist('Example Artist', track), 'bad_version')


if __name__ == '__main__':
    unittest.main()
