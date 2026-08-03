import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('SETLIST_API_KEY', 'test')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'spotify_gmm_2026'))

import youtube_music_transfer as transfer


class YouTubeMusicTransferTest(unittest.TestCase):
    def test_parse_report_tracks_deduplicates_artist_title_pairs(self):
        report = {
            'report': [
                {
                    'artist': 'Example Artist',
                    'query_artist': 'Example Artist',
                    'tracks': ['Example Artist - Song - 2024 Remaster', 'Example Artist - Song'],
                }
            ]
        }

        tracks = transfer.parse_report_tracks(report)

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]['title'], 'Song - 2024 Remaster')

    def test_candidate_score_accepts_clean_song_match(self):
        query = {
            'artist': 'Example Artist',
            'query_artist': 'Example Artist',
            'lineup_artist': 'Example Artist',
            'title': 'Clean Song',
        }
        candidate = {
            'title': 'Clean Song',
            'videoId': 'video-id',
            'resultType': 'song',
            'duration_seconds': 180,
            'artists': [{'name': 'Example Artist'}],
        }

        self.assertIsNotNone(transfer.youtube_candidate_score(query, candidate))

    def test_candidate_score_rejects_live_version(self):
        query = {
            'artist': 'Example Artist',
            'query_artist': 'Example Artist',
            'lineup_artist': 'Example Artist',
            'title': 'Clean Song',
        }
        candidate = {
            'title': 'Clean Song - Live at Wacken',
            'videoId': 'video-id',
            'resultType': 'song',
            'duration_seconds': 180,
            'artists': [{'name': 'Example Artist'}],
        }

        self.assertIsNone(transfer.youtube_candidate_score(query, candidate))

    def test_candidate_score_rejects_youtube_specific_bad_version(self):
        query = {
            'artist': 'Example Artist',
            'query_artist': 'Example Artist',
            'lineup_artist': 'Example Artist',
            'title': 'Clean Song',
        }
        candidate = {
            'title': 'Clean Song (Club Version)',
            'videoId': 'video-id',
            'resultType': 'song',
            'duration_seconds': 180,
            'artists': [{'name': 'Example Artist'}],
        }

        self.assertIsNone(transfer.youtube_candidate_score(query, candidate))

    def test_candidate_score_accepts_version_when_source_requested_it(self):
        query = {
            'artist': 'Example Artist',
            'query_artist': 'Example Artist',
            'lineup_artist': 'Example Artist',
            'title': 'Clean Song (Club Version)',
        }
        candidate = {
            'title': 'Clean Song (Club Version)',
            'videoId': 'video-id',
            'resultType': 'song',
            'duration_seconds': 180,
            'artists': [{'name': 'Example Artist'}],
        }

        self.assertIsNotNone(transfer.youtube_candidate_score(query, candidate))

    def test_build_report_counts_duplicates_and_missing(self):
        source = {'festival': 'Example', 'playlist_name': 'Example', 'playlist_url': 'spotify-url'}
        matched = [
            {'label': 'A - Song', 'title': 'Song', 'videoId': 'same'},
            {'label': 'B - Song', 'title': 'Song', 'videoId': 'same'},
        ]

        report = transfer.build_youtube_report(source, matched, matched, [{'label': 'missing'}])

        self.assertEqual(report['matched_track_count'], 2)
        self.assertEqual(report['missing_track_count'], 1)
        self.assertEqual(report['duplicate_video_ids'], ['same'])
        self.assertEqual(report['duplicate_song_keys'], ['B - Song'])


if __name__ == '__main__':
    unittest.main()
