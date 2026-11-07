"""Review axes: one prompt file per axis in prompts/axes/, with a YAML front matter."""

from dataclasses import dataclass
from pathlib import Path

import yaml

AXES_DIR = Path(__file__).parent / "prompts" / "axes"


@dataclass(frozen=True)
class Axis:
    key: str
    label: str
    rules: tuple[str, ...]  # rule ids the axis mainly applies, listed first in its prompt
    docs: tuple[str, ...]  # glob patterns, relative to the repository root, inlined in the prompt
    derogable: bool  # False: its findings are never dismissed by a derogation
    body: str


def parse_axis(key: str, text: str) -> Axis:
    """Parse an axis prompt: a `---` YAML front matter (label, rules, docs, derogable), then the prompt."""
    if not text.startswith("---\n"):
        raise ValueError(f"axis '{key}': missing front matter")
    header_text, separator, body = text[4:].partition("\n---\n")
    if not separator:
        raise ValueError(f"axis '{key}': unterminated front matter")
    try:
        header = yaml.safe_load(header_text) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"axis '{key}': invalid front matter: {error}") from error
    if not isinstance(header, dict) or "label" not in header:
        raise ValueError(f"axis '{key}': the front matter needs a label")
    return Axis(
        key=key,
        label=str(header["label"]),
        rules=tuple(header.get("rules") or ()),
        docs=tuple(header.get("docs") or ()),
        derogable=bool(header.get("derogable", True)),
        body=body.strip(),
    )


def load_axes(axes_dir: Path = AXES_DIR, only: list[str] | None = None) -> list[Axis]:
    """Every axis of the directory, by file name; `only` keeps the named ones (unknown names raise)."""
    axes = [parse_axis(path.stem, path.read_text(encoding="utf-8")) for path in sorted(axes_dir.glob("*.md"))]
    if only is None:
        return axes
    unknown = sorted(set(only) - {axis.key for axis in axes})
    if unknown:
        raise ValueError(f"unknown axes: {', '.join(unknown)} (available: {', '.join(a.key for a in axes)})")
    return [axis for axis in axes if axis.key in only]
