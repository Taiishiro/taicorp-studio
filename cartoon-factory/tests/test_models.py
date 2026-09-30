"""Validation du script, sérialisation, fiches perso."""

from cartoon_factory.models import Episode, Shot, ValidationError
from cartoon_factory.stage_script import slugify


def test_example_episode_is_valid(example_episode, example_characters):
    assert example_episode.validate(known_characters=set(example_characters)) == []
    assert 30 <= example_episode.total_duration_s() <= 120


def test_roundtrip(tmp_path, example_episode):
    p = tmp_path / "ep.json"
    example_episode.save(p)
    again = Episode.load(p)
    assert again.to_dict() == example_episode.to_dict()
    assert again.shots[0].keyframes[1].prompt.startswith("Pilou")


def test_validation_catches_problems():
    ep = Episode(id="Bad Id!", question="", characters=[], shots=[
        Shot(id="s01", voice_text=" ".join(["mot"] * 40), visual="", duration_s=4,
             method="magic", camera="orbit", characters=["ghost"]),
        Shot(id="s01", voice_text="x", visual="y", duration_s=30),
    ])
    problems = ep.validate(known_characters=set())
    joined = "\n".join(problems)
    for needle in ("id d'épisode", "question vide", "method", "camera", "doublon", "durée 30",
                   "visuelle vide", "trop dense", "absent de episode.characters",
                   "pas de fiche perso"):
        assert needle in joined, needle
    try:
        ep.validate_or_raise()
    except ValidationError as exc:
        assert len(exc.problems) >= 8
    else:
        raise AssertionError("ValidationError attendue")


def test_tooncrafter_needs_two_keyframes():
    s = Shot(id="s01", voice_text="a", visual="b", method="tooncrafter")
    assert s.keyframe_count == 2
    assert Shot(id="s02", voice_text="a", visual="b", method="wan_i2v").keyframe_count == 1


def test_slugify():
    assert slugify("Pourquoi le ciel est bleu ?") == "pourquoi-le-ciel-est-bleu"
    assert slugify("Où vont les étoiles le jour ?!") == "ou-vont-les-etoiles-le-jour"
