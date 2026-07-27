import importlib.util
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
        'id': name.lower().replace(' ', '-'),
    }


class TrackFilterTest(unittest.TestCase):
    def test_import_without_setlist_key_for_offline_analysis(self):
        module_path = Path(__file__).resolve().parents[1] / 'scripts' / 'spotify_gmm_2026' / 'festival_playlists.py'

        with patch.dict(os.environ, {}, clear=True):
            spec = importlib.util.spec_from_file_location('festival_playlists_no_key', module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

        self.assertIsNone(module.SETLIST_API_KEY)
        self.assertNotIn('x-api-key', module.SETLIST_HEADERS)
        with self.assertRaisesRegex(RuntimeError, 'SETLIST_API_KEY is required'):
            module.require_setlist_api_key()

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

    def test_skips_two_token_partial_artist_match(self):
        track = make_track(artists=['Victor Ray'])

        self.assertEqual(playlists.should_skip_track_for_artist('Kay Ray', track), 'primary_artist_mismatch')

    def test_skips_two_token_partial_artist_match_in_fallback(self):
        track = make_track(artists=['Metal Carter'])

        self.assertEqual(playlists.should_skip_track_for_artist('Metal Karate', track), 'primary_artist_mismatch')

    def test_accepts_lineup_artist_with_featuring_clause_as_base_artist(self):
        track = make_track(artists=['Sex Pistols'])

        self.assertIsNone(playlists.should_skip_track_for_artist('Sex Pistols featuring Frank Carter', track))

    def test_setlist_lookup_strips_featuring_clause(self):
        self.assertEqual(playlists.setlist_lookup_name('Sex Pistols featuring Frank Carter'), 'Sex Pistols')

    def test_single_token_mbid_search_requires_exact_artist_name(self):
        response = {'artist': [{'name': 'Twilight Force', 'mbid': 'twilight-force-mbid'}]}

        playlists.MBID_CACHE.clear()
        with patch.object(playlists, 'sl_get', return_value=response):
            self.assertIsNone(playlists.search_artist_mbid('Force'))

    def test_single_token_mbid_search_accepts_exact_artist_name(self):
        response = {'artist': [{'name': 'Force', 'mbid': 'force-mbid'}]}

        playlists.MBID_CACHE.clear()
        with patch.object(playlists, 'sl_get', return_value=response):
            self.assertEqual(playlists.search_artist_mbid('Force'), 'force-mbid')

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

    def test_tom_morello_accepts_live_repertoire_primary_artists(self):
        for primary_artist in ['Tom Morello', 'Rage Against The Machine', 'Audioslave', 'Prophets Of Rage']:
            with self.subTest(primary_artist=primary_artist):
                track = make_track(artists=[primary_artist])

                self.assertIsNone(playlists.should_skip_track_for_artist('Tom Morello', track, 'Tom Morello'))

    def test_tom_morello_setlist_search_includes_live_repertoire_artists(self):
        calls = []
        rage_track = make_track(name='Bulls On Parade', artists=['Rage Against The Machine'])
        rage_track.update({'uri': 'spotify:track:rage', 'popularity': 80, 'id': 'rage'})

        def fake_spotify_get(_url, params):
            calls.append(params['q'])
            if params['q'] == 'track:Bulls On Parade artist:Rage Against The Machine':
                return {'tracks': {'items': [rage_track]}}
            return {'tracks': {'items': []}}

        with patch.object(playlists, 'spotify_get', side_effect=fake_spotify_get):
            result = playlists.spotify_search_track('Tom Morello', 'Bulls On Parade', 'Tom Morello')

        self.assertEqual(result['uri'], 'spotify:track:rage')
        self.assertIn('track:Bulls On Parade artist:Rage Against The Machine', calls)

    def test_montreal_rejects_of_montreal_prefix_match(self):
        track = make_track(artists=['of Montreal'])

        self.assertEqual(
            playlists.should_skip_track_for_artist('Montreal', track, 'Montreal'),
            'primary_artist_mismatch',
        )

    def test_identical_fallback_names_are_searched_once_with_ten_tracks(self):
        festival = playlists.Festival(
            key='fallback_test',
            display_name='Fallback Test',
            playlist_name='Fallback Test',
            description='Fallback Test',
            lineup_fn=lambda: (['Example Artist'], []),
            existing_playlist_id='playlist-id',
        )
        tracks = []
        for index in range(1, 6):
            track = make_track(name=f'Song {index}', artists=['Example Artist'])
            track.update({'uri': f'spotify:track:{index}', 'popularity': 100 - index})
            tracks.append(track)

        with patch.object(playlists, 'search_artist_mbid', return_value=None), \
                patch.object(playlists, 'get_followers', return_value=1), \
                patch.object(playlists, 'spotify_top_tracks', return_value=({'id': 'artist-id'}, tracks)) as top_tracks, \
                patch.object(playlists, 'update_playlist_details'), \
                patch.object(playlists, 'playlist_replace_all'):
            playlists.build_playlist(festival, 'user-id')

        top_tracks.assert_called_once_with('Example Artist', 10, artist_id=None)

    def test_setlist_tracks_sort_by_recent_plays_before_spotify_popularity(self):
        frequent = make_track(name='Frequent Song')
        popular = make_track(name='Popular Song')

        ranked = sorted([
            (95, 2, 'Popular Song', popular),
            (50, 5, 'Frequent Song', frequent),
        ], key=playlists.setlist_track_sort_key)

        self.assertEqual(ranked[0][2], 'Frequent Song')

    def test_live_word_inside_song_title_is_not_live_version(self):
        track = make_track(name='Live It Up', artists=['Example Artist'])

        self.assertEqual(playlists.track_version_penalty(track), 0)
        self.assertIsNone(playlists.should_skip_track_for_artist('Example Artist', track))

    def test_live_version_marker_is_penalized(self):
        track = make_track(name='Clean Song - Live at Wacken', artists=['Example Artist'])

        self.assertEqual(playlists.track_version_penalty(track), 2)
        self.assertEqual(playlists.should_skip_track_for_artist('Example Artist', track), 'bad_version')

    def test_edit_version_marker_is_rejected(self):
        track = make_track(name='Clean Song - edit', artists=['Example Artist'])

        self.assertEqual(playlists.track_version_penalty(track), 2)
        self.assertEqual(playlists.should_skip_track_for_artist('Example Artist', track), 'bad_version')

    def test_radio_and_extended_versions_are_rejected(self):
        radio = make_track(name='Clean Song - Radio Version', artists=['Example Artist'])
        extended = make_track(name='Clean Song - Extended Version', artists=['Example Artist'])

        self.assertEqual(playlists.should_skip_track_for_artist('Example Artist', radio), 'bad_version')
        self.assertEqual(playlists.should_skip_track_for_artist('Example Artist', extended), 'bad_version')

    def test_named_album_version_is_not_rejected(self):
        track = make_track(name='Everytime We Touch - TEKKNO Version', artists=['Example Artist'])

        self.assertEqual(playlists.track_version_penalty(track), 0)
        self.assertIsNone(playlists.should_skip_track_for_artist('Example Artist', track))

    def test_wacken_excludes_non_band_listing_entries(self):
        festival = playlists.Festival(
            key='wacken_test',
            display_name='Wacken Test',
            playlist_name='Wacken Test',
            description='Wacken Test',
            lineup_fn=lambda: ([], []),
            extra_excludes={
                'Acoustic Guerillas feat Ellerbek Pussyboys',
                'Acoustic Steel',
                'Bastian Zach',
                'Blaas of Glory',
                'Jazz Sabbath',
                'Kay Ray',
                'Lesung: Maxim Matthew "Frøstfǽdrin- Der Ruf des weißen Greifen"',
                'Metal Karate',
                'Metal Battle tba.',
                'System of a Down by Anett & Livi Acoustic + Radó Éden',
                'The Ukeboys',
                'Tribute2Wacken',
                'Vika Goes Wild',
                'Wildcover',
            },
        )

        for artist in festival.extra_excludes:
            self.assertTrue(playlists.should_exclude(artist, festival))


if __name__ == '__main__':
    unittest.main()
