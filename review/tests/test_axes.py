from pathlib import Path

import pytest

from review.axes import load_axes, parse_axis


def test_axis_front_matter_gives_label_rules_docs_and_derogability() -> None:
    axis = parse_axis(
        "security",
        "---\nlabel: Security\nrules: [rule-23]\ndocs: [doc/a.md]\nderogable: false\n---\n# Your axis\n\nCheck.\n",
    )
    assert (axis.label, axis.rules, axis.docs, axis.derogable) == ("Security", ("rule-23",), ("doc/a.md",), False)
    assert axis.body == "# Your axis\n\nCheck."


def test_axis_is_derogable_and_without_docs_by_default() -> None:
    axis = parse_axis("naming", "---\nlabel: Naming\n---\nbody")
    assert (axis.rules, axis.docs, axis.derogable) == ((), (), True)


@pytest.mark.parametrize(
    "text",
    ["# no front matter", "---\nlabel: x\nno end", "---\nrules: []\n---\nbody", "---\nlabel: [x\n---\nbody"],
)
def test_malformed_axis_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_axis("bad", text)


def test_only_keeps_the_named_axes_and_refuses_unknown_ones(tmp_path: Path) -> None:
    for key in ("a", "b"):
        (tmp_path / f"{key}.md").write_text(f"---\nlabel: {key}\n---\nbody", encoding="utf-8")
    assert [axis.key for axis in load_axes(tmp_path, only=["b"])] == ["b"]
    with pytest.raises(ValueError, match="unknown axes: c"):
        load_axes(tmp_path, only=["c"])


def test_only_the_security_axis_cannot_be_waived() -> None:
    assert [axis.key for axis in load_axes() if not axis.derogable] == ["security"]
