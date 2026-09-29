"""Current protocol must preserve the frozen experiment identities and signals."""
import importlib

import pytest

from workflows.disturbance_protocol import get_protocol


VERSIONS = ("v86", "v87", "v88")
ORIGINAL = {version: importlib.import_module(f"workflows.protocol_{version}")
            for version in VERSIONS}
CASES = [(version, case) for version in VERSIONS
         for case in ORIGINAL[version].cases()]


@pytest.mark.parametrize("version", VERSIONS)
def test_frozen_protocol_identity(version):
    current = get_protocol(version)
    assert current.VERSION == version
    assert current.COLLECTOR == "workflows.collect_disturbance_data"
    assert current.cases() == ORIGINAL[version].cases()
    assert current.protocol() == ORIGINAL[version].protocol()
    assert current.RIDGE == getattr(ORIGINAL[version], "RIDGE", None)


@pytest.mark.parametrize("version,case", CASES,
                         ids=[case["run_id"] for _, case in CASES])
def test_all_frozen_waveforms_are_byte_identical(version, case):
    expected = ORIGINAL[version].excitation(case)
    actual = get_protocol(version).excitation(case)
    assert actual.shape == expected.shape
    assert actual.dtype == expected.dtype
    assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize("version", VERSIONS)
def test_rejects_modified_case(version):
    case = get_protocol(version).cases()[0]
    case["seed"] += 1000
    with pytest.raises(ValueError, match=f"{version}_case"):
        get_protocol(version).excitation(case)


@pytest.mark.parametrize("version", VERSIONS)
def test_callers_cannot_mutate_frozen_protocol(version):
    current = get_protocol(version)
    protocol = current.protocol()
    protocol["cases"][0]["seed"] = -1
    current.cases().clear()
    assert current.protocol() == ORIGINAL[version].protocol()


def test_default_and_invalid_version():
    assert get_protocol().VERSION == "v88"
    with pytest.raises(ValueError, match="disturbance_protocol_version"):
        get_protocol("../v87")


@pytest.mark.parametrize("version", VERSIONS)
def test_split_rejects_cross_role_episode(version):
    current = get_protocol(version)
    groups = [[case for case in current.cases() if case["role"] == role]
              for role in ("train", "validation", "test")]
    current.validate_split(*groups)
    groups[0].append(groups[2][0])
    with pytest.raises(ValueError, match=f"{version}_episode_split"):
        current.validate_split(*groups)


def test_matrix_levels_share_the_same_waveform_for_each_seed():
    current = get_protocol("v88")
    outputs = {}
    for case in current.cases():
        signal = current.excitation(case).tobytes()
        assert outputs.setdefault(case["seed"], signal) == signal
