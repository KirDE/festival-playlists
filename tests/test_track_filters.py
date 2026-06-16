import os
import sys
import unittest
from pathlib import Path

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

    def test_accepts_primary_artist_match_with_featured_guests(self):
        track = make_track(artists=['Anna Grey', 'Kontra K'])

        self.assertIsNone(playlists.should_skip_track_for_artist('Anna Grey', track))

    def test_accepts_alias_primary_artist_match(self):
        track = make_track(artists=['Cavalera Conspiracy'])

        self.assertIsNone(playlists.should_skip_track_for_artist('Cavalera', track))


if __name__ == '__main__':
    unittest.main()
