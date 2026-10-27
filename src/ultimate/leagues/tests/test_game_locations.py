from datetime import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from ultimate.leagues.models import League


class GameLocationsTest(SimpleTestCase):
    def test_null_start_times_sort_after_scheduled_games(self):
        field = SimpleNamespace(pk=1, name="Field")
        games = [
            self._game(field, field_name_pk=1, field_name="A", start=None),
            self._game(
                field,
                field_name_pk=2,
                field_name="B",
                start=datetime(2026, 1, 5, 19, 0),
            ),
            self._game(field, field_name_pk=3, field_name="C", start=None),
        ]

        locations = League().get_game_locations(games=games)

        self.assertEqual(
            [location["start"] for location in locations],
            [datetime(2026, 1, 5, 19, 0).time(), None, None],
        )

    @staticmethod
    def _game(field, field_name_pk, field_name, start):
        return SimpleNamespace(
            start=start,
            field_name=SimpleNamespace(
                pk=field_name_pk,
                name=field_name,
                field=field,
            ),
        )
