"""The engine-support registry (`ravel.support.FEATURE_SUPPORT`) must stay in
lock-step with the real feature names. Every key has to name an actual feature —
a base-class feature, a subclass feature, or a race-trait label — so a typo or a
renamed feature is caught instead of silently badging nothing. And every status
must be one of the four the UI knows how to render."""
from ravel.character import CLASS_FEATURES, RACES, SUBCLASSES
from ravel.support import FEATURE_SUPPORT, VALID_STATUSES
from web.builder import _race_traits


def _known_feature_names() -> set[str]:
    names: set[str] = set()
    for levels in CLASS_FEATURES.values():
        for feats in levels.values():
            names.update(feats)
    for sub in SUBCLASSES.values():
        for feats in sub.features.values():
            names.update(feats)
    for race in RACES.values():
        names.update(_race_traits(race))
    return names


def test_every_key_names_a_real_feature():
    known = _known_feature_names()
    unknown = sorted(k for k in FEATURE_SUPPORT if k not in known)
    assert not unknown, f"FEATURE_SUPPORT keys with no matching feature/trait: {unknown}"


def test_every_status_is_valid():
    assert VALID_STATUSES == {"approx", "gap", "utility", "cosmetic"}
    for name, entry in FEATURE_SUPPORT.items():
        assert entry["status"] in VALID_STATUSES, f"{name}: bad status {entry['status']!r}"
        assert entry.get("note"), f"{name}: missing note"
