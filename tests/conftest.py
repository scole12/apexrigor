"""Test boundary: no test may reach an email provider or spawn a production mail dispatcher.

Production code stays production code. This autouse fixture lives only in the test tree and
turns any attempt to call SendGrid/Resend, or to spawn a mail dispatcher without --dry-run,
into a test failure. 2026-10-02: controller and publisher tests sent real email through the
real transport; this is the test-side stop for that class of defect.
"""
import subprocess
import urllib.request

import pytest

BLOCKED_HOSTS = ("api.sendgrid.com", "api.resend.com")
BLOCKED_DISPATCHERS = ("apex_send_email_dispatch.py", "apex_mma_send_email_dispatch.py", "apex_notify.py")


def _url_text(target):
    return getattr(target, "full_url", None) or str(target)


@pytest.fixture(autouse=True)
def no_external_mail(monkeypatch):
    real_urlopen = urllib.request.urlopen
    real_popen = subprocess.Popen

    def urlopen(url, *args, **kwargs):
        text = _url_text(url)
        if any(host in text for host in BLOCKED_HOSTS):
            raise AssertionError("TEST_BOUNDARY: test attempted a live mail-provider call: " + text)
        return real_urlopen(url, *args, **kwargs)

    class Popen(real_popen):
        def __init__(self, args, *a, **k):
            command = " ".join(str(part) for part in args) if isinstance(args, (list, tuple)) else str(args)
            if any(name in command for name in BLOCKED_DISPATCHERS) and "--dry-run" not in command:
                raise AssertionError("TEST_BOUNDARY: test attempted to spawn a production mail dispatcher: " + command[:200])
            if "api.sendgrid.com" in command:
                raise AssertionError("TEST_BOUNDARY: test attempted a live SendGrid call via subprocess")
            super().__init__(args, *a, **k)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(subprocess, "Popen", Popen)
    try:
        import requests.sessions
    except ImportError:
        return
    real_request = requests.sessions.Session.request

    def request(self, method, url, *args, **kwargs):
        if any(host in str(url) for host in BLOCKED_HOSTS):
            raise AssertionError("TEST_BOUNDARY: test attempted a live mail-provider call: " + str(url))
        return real_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(requests.sessions.Session, "request", request)
