import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_contributions as fc  # noqa: E402


def payload():
    return {
        "data": {
            "user": {
                "repositories": {"totalCount": 5},
                "contributionsCollection": {
                    "contributionCalendar": {
                        "totalContributions": 3,
                        "weeks": [
                            {"contributionDays": [{"date": "2026-11-02", "contributionCount": 1}]},
                            {"contributionDays": [{"date": "2026-11-01", "contributionCount": 2}]},
                        ],
                    }
                },
            }
        }
    }


def test_parse_flattens_and_sorts_days():
    data = fc.parse(payload(), "someone")
    assert data == {
        "login": "someone",
        "public_repos": 5,
        "total": 3,
        "days": [{"date": "2026-11-01", "count": 2}, {"date": "2026-11-02", "count": 1}],
    }


def test_parse_rejects_api_errors_and_unknown_user():
    with pytest.raises(ValueError):
        fc.parse({"errors": [{"message": "Bad credentials"}]}, "someone")
    with pytest.raises(ValueError):
        fc.parse({"data": {"user": None}}, "someone")


def test_missing_token_keeps_existing_file(monkeypatch, tmp_path):
    existing = tmp_path / "contributions.json"
    existing.write_text('{"keep": true}', encoding="utf-8")
    monkeypatch.setattr(fc, "OUT", existing)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert fc.main() == 1
    assert existing.read_text(encoding="utf-8") == '{"keep": true}'
