"""System-integrity smoke tests.

Two cheap but high-signal guards for the upgrade:

* ``check --deploy``-free system checks must pass (deprecated settings, bad admin
  config, and removed-feature usage surface here as the Django version climbs).
* The models and the migration graph must agree -- no field change (e.g. adding
  ``on_delete`` or ``DEFAULT_AUTO_FIELD`` shifts) should leave an un-generated
  migration behind. ``makemigrations --check`` fails the run if one is missing.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import TestCase


class SystemCheckTest(TestCase):
    def test_system_checks_pass(self):
        try:
            call_command("check")
        except SystemCheckError as exc:  # pragma: no cover - failure path
            self.fail("manage.py check reported issues:\n{}".format(exc))

    def test_no_missing_migrations(self):
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit as exc:
            # --check exits non-zero when migrations are missing.
            self.fail(
                "Missing migrations detected by makemigrations --check:\n{}".format(out.getvalue())
            )
