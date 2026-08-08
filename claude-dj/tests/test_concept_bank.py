import json
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from mix_director import load_concept


def test_load_concept_returns_dict_for_valid_slug():
    c = load_concept("sunrise")
    assert isinstance(c, dict)
    assert c["name"] == "sunrise"
    assert "prompt_injection" in c
    assert "directives" in c


def test_load_concept_returns_none_for_missing_slug():
    assert load_concept("nonexistent_concept_xyz") is None


def test_all_concepts_have_required_fields():
    concept_dir = Path(__file__).parent.parent / "concept_bank"
    required = {"name", "display_name", "description", "prompt_injection", "directives"}
    directive_keys = {"preferred_overlap_bars", "preferred_technique", "avoid_technique", "bass_swap_placement"}

    for path in concept_dir.glob("*.json"):
        data = json.loads(path.read_text())
        missing = required - data.keys()
        assert not missing, f"{path.name} missing fields: {missing}"
        missing_directives = directive_keys - data["directives"].keys()
        assert not missing_directives, f"{path.name} missing directives: {missing_directives}"


def test_all_concepts_have_valid_bass_swap_placement():
    concept_dir = Path(__file__).parent.parent / "concept_bank"
    valid = {"early", "mid", "late"}
    for path in concept_dir.glob("*.json"):
        data = json.loads(path.read_text())
        placement = data["directives"]["bass_swap_placement"]
        assert placement in valid, f"{path.name}: invalid bass_swap_placement={placement!r}"


def test_all_concepts_have_valid_preferred_technique():
    concept_dir = Path(__file__).parent.parent / "concept_bank"
    valid = {"blend", "cut", "drop_swap"}
    for path in concept_dir.glob("*.json"):
        data = json.loads(path.read_text())
        tech = data["directives"]["preferred_technique"]
        assert tech in valid, f"{path.name}: invalid preferred_technique={tech!r}"
