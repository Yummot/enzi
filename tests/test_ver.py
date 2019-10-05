"""
enzi.ver module test
based on rust semver VersionReq tests
"""

import pytest
import semver
import typing
from semver import VersionInfo
from enzi.ver import VersionReq, Predicate, ReqOp


def req(s: str):
    return VersionReq.parse(s)


def version(s: str):
    return VersionInfo.parse(s)


def assert_match(req: VersionReq, vers: typing.Iterable[str]):
    for ver in vers:
        assert req.matches(version(ver)), "didn't match {}".format(ver)


def assert_not_match(req: VersionReq, vers: typing.Iterable[str]):
    for ver in vers:
        assert not req.matches(version(ver)), "matched {}".format(ver)


def calculate_hash(t: typing.Hashable):
    return hash(t)


def test_parsing_default():
    r = req("1.0.0")
    assert str(r) == "^1.0.0"
    assert_match(r, ["1.0.0", "1.0.1"])
    assert_not_match(r, ["0.9.9", "0.10.0", "0.1.0"])


def test_parsing_exact():
    r = req("=1.0.0")
    assert str(r) == "= 1.0.0"
    assert_match(r, ["1.0.0"])
    assert_not_match(r, ["1.0.1", "0.9.9", "0.10.0", "0.1.0", "1.0.0-pre"])

    r = req("=0.9.0")
    assert str(r) == "= 0.9.0"
    assert_match(r, ["0.9.0"])
    assert_not_match(r, ["0.9.1", "1.9.0", "0.0.9"])

    r = req("=0.1.0-beta2.a")
    assert str(r) == "= 0.1.0-beta2.a"
    assert_match(r, ["0.1.0-beta2.a"])
    assert_not_match(r, ["0.9.1", "0.1.0", "0.1.1-beta2.a", "0.1.0-beta2"])


def test_parsing_greater_x():
    r = req(">=1.0.0")
    assert str(r) == ">= 1.0.0"
    assert_match(r, ["1.0.0", "2.0.0"])
    assert_not_match(r, ["0.1.0", "0.0.1", "1.0.0-pre", "2.0.0-pre"])

    r = req(">= 2.1.0-alpha2")
    assert_match(r, ["2.1.0-alpha2", "2.1.0-alpha3", "2.1.0", "3.0.0"])
    assert_not_match(
        r,
        ["2.0.0", "2.1.0-alpha1", "2.0.0-alpha2", "3.0.0-alpha2"],
    )


def test_parsing_less_x():
    r = req("<1.0.0")
    assert str(r) == "< 1.0.0"
    assert_match(r, ["0.1.0", "0.0.1"])
    assert_not_match(r, ["1.0.0", "1.0.0-beta", "1.0.1", "0.9.9-alpha"])

    r = req("<= 2.1.0-alpha2")
    assert_match(r, ["2.1.0-alpha2", "2.1.0-alpha1", "2.0.0", "1.0.0"])
    assert_not_match(
        r,
        ["2.1.0", "2.2.0-alpha1", "2.0.0-alpha2", "1.0.0-alpha2"],
    )


def test_parsing_less_failed_case0():
    with pytest.raises(ValueError) as excinfo:
        VersionReq.parse("> 0.1.0,")
    assert excinfo.type == ValueError


def test_parsing_less_failed_case1():
    with pytest.raises(ValueError) as excinfo:
        VersionReq.parse("> 0.3.0, ,")
    assert excinfo.type == ValueError


def test_multiple():
    r = req("> 0.0.9, <= 2.5.3")
    assert str(r) == "> 0.0.9, <= 2.5.3"
    assert_match(r, ["0.0.10", "1.0.0", "2.5.3"])
    assert_not_match(r, ["0.0.8", "2.5.4"])

    r = req("0.3.0, 0.4.0")
    assert str(r) == "^0.3.0, ^0.4.0"
    assert_not_match(r, ["0.0.8", "0.3.0", "0.4.0"])

    r = req("<= 0.2.0, >= 0.5.0")
    assert str(r) == "<= 0.2.0, >= 0.5.0"
    assert_not_match(r, ["0.0.8", "0.3.0", "0.5.1"])

    r = req("0.1.0, 0.1.4, 0.1.6")
    assert str(r) == "^0.1.0, ^0.1.4, ^0.1.6"
    assert_match(r, ["0.1.6", "0.1.9"])
    assert_not_match(r, ["0.1.0", "0.1.4", "0.2.0"])

    r = req(">=0.5.1-alpha3, <0.6")
    assert str(r) == ">= 0.5.1-alpha3, < 0.6"
    assert_match(
        r,
        [
            "0.5.1-alpha3",
            "0.5.1-alpha4",
            "0.5.1-beta",
            "0.5.1",
            "0.5.5",
        ],
    )
    assert_not_match(
        r,
        ["0.5.1-alpha1", "0.5.2-alpha3", "0.5.5-pre", "0.5.0-pre"],
    )
    assert_not_match(r, ["0.6.0", "0.6.0-pre"])


def test_parsing_tilde():
    r = req("~1")
    assert_match(r, ["1.0.0", "1.0.1", "1.1.1"])
    assert_not_match(r, ["0.9.1", "2.9.0", "0.0.9"])

    r = req("~1.2")
    assert_match(r, ["1.2.0", "1.2.1"])
    assert_not_match(r, ["1.1.1", "1.3.0", "0.0.9"])

    r = req("~1.2.2")
    assert_match(r, ["1.2.2", "1.2.4"])
    assert_not_match(r, ["1.2.1", "1.9.0", "1.0.9", "2.0.1", "0.1.3"])

    r = req("~1.2.3-beta.2")
    assert_match(r, ["1.2.3", "1.2.4", "1.2.3-beta.2", "1.2.3-beta.4"])
    assert_not_match(r, ["1.3.3", "1.1.4", "1.2.3-beta.1", "1.2.4-beta.2"])

def test_parsing_compatible():
    r = req("^1")
    assert_match(r, ["1.1.2", "1.1.0", "1.2.1", "1.0.1"])
    assert_not_match(r, ["0.9.1", "2.9.0", "0.1.4"])
    assert_not_match(r, ["1.0.0-beta1", "0.1.0-alpha", "1.0.1-pre"])

    r = req("^1.1")
    assert_match(r, ["1.1.2", "1.1.0", "1.2.1"])
    assert_not_match(r, ["0.9.1", "2.9.0", "1.0.1", "0.1.4"])

    r = req("^1.1.2")
    assert_match(r, ["1.1.2", "1.1.4", "1.2.1"])
    assert_not_match(r, ["0.9.1", "2.9.0", "1.1.1", "0.0.1"])
    assert_not_match(r, ["1.1.2-alpha1", "1.1.3-alpha1", "2.9.0-alpha1"])

    r = req("^0.1.2")
    assert_match(r, ["0.1.2", "0.1.4"])
    assert_not_match(r, ["0.9.1", "2.9.0", "1.1.1", "0.0.1"])
    assert_not_match(r, ["0.1.2-beta", "0.1.3-alpha", "0.2.0-pre"])

    r = req("^0.5.1-alpha3")
    assert_match(
        r,
        [
            "0.5.1-alpha3",
            "0.5.1-alpha4",
            "0.5.1-beta",
            "0.5.1",
            "0.5.5",
        ],
    )
    assert_not_match(
        r,
        [
            "0.5.1-alpha1",
            "0.5.2-alpha3",
            "0.5.5-pre",
            "0.5.0-pre",
            "0.6.0",
        ],
    )

    r = req("^0.0.2")
    assert_match(r, ["0.0.2"])
    assert_not_match(r, ["0.9.1", "2.9.0", "1.1.1", "0.0.1", "0.1.4"])

    r = req("^0.0")
    assert_match(r, ["0.0.2", "0.0.0"])
    assert_not_match(r, ["0.9.1", "2.9.0", "1.1.1", "0.1.4"])

    r = req("^0")
    assert_match(r, ["0.9.1", "0.0.2", "0.0.0"])
    assert_not_match(r, ["2.9.0", "1.1.1"])

    r = req("^1.4.2-beta.5")
    assert_match(
        r,
        ["1.4.2", "1.4.3", "1.4.2-beta.5", "1.4.2-beta.6", "1.4.2-c"],
    )
    assert_not_match(
        r,
        [
            "0.9.9",
            "2.0.0",
            "1.4.2-alpha",
            "1.4.2-beta.4",
            "1.4.3-beta.5",
        ],
    )

def test_any():
    r = VersionReq.any()
    assert_match(r, ["0.0.1", "0.1.0", "1.0.0"])

def test_pre():
    r = req("=2.1.1-really.0")
    assert_match(r, ["2.1.1-really.0"])

def test_from_str():
    assert str(VersionReq.parse("1.0.0")) == "^1.0.0"
    assert str(VersionReq.parse("=1.0.0")) == "= 1.0.0"
    assert str(VersionReq.parse("~1")) == "~1"
    assert str(VersionReq.parse("~1.2")) == "~1.2"
    assert str(VersionReq.parse("^1")) == "^1"
    assert str(VersionReq.parse("^1.1")) == "^1.1"
    assert str(VersionReq.parse("< 1.0.0")) == "< 1.0.0"

def test_eq_hash():
    assert req("^1") == req("^1")
    assert calculate_hash(req("^1")) == calculate_hash(req("^1"))
