#!/usr/bin/env python3
"""Validate an installed D2D/D3D partitioner tree."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


FORBIDDEN_CUDA_LIBRARIES = ("libcudart", "libtorch_cuda", "libc10_cuda")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(text)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def git_revision(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def source_revision(path: Path) -> str | None:
    vendored_manifest = path / ".taiwei-vendored-source.json"
    if vendored_manifest.exists():
        try:
            payload = json.loads(vendored_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"invalid vendored source manifest: {vendored_manifest}"
            ) from error
        revision = payload.get("d2d_revision")
        if not isinstance(revision, str) or not revision:
            raise RuntimeError(
                f"vendored source manifest has no D2D revision: {vendored_manifest}"
            )
        return revision
    return git_revision(path)


def check_cpu_only_linkage(prefix: Path) -> int:
    extensions = sorted(prefix.rglob("*.so"))
    if not extensions:
        raise RuntimeError(f"installed tree contains no compiled extensions: {prefix}")
    for extension in extensions:
        try:
            result = subprocess.run(
                ["ldd", str(extension)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as error:
            raise RuntimeError("ldd is required for CPU-only linkage checks") from error
        linkage = result.stdout.lower()
        forbidden = [name for name in FORBIDDEN_CUDA_LIBRARIES if name in linkage]
        if forbidden:
            raise RuntimeError(
                f"CUDA libraries linked by {extension}: {', '.join(forbidden)}"
            )
    return len(extensions)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--require-manifest", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    prefix = args.prefix.resolve()
    d3d_root = prefix / "thirdparty" / "Differentiable-3D-Partitioner"
    required_paths = (
        prefix / "placer" / "d2d_placer.py",
        prefix / "dreamplace" / "ops" / "place_io",
        d3d_root / "partitioner" / "core" / "flow.py",
        d3d_root / "configs",
    )
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise RuntimeError("installed files are missing: " + ", ".join(missing))

    os.chdir(prefix)
    for path in (d3d_root, prefix / "placer", prefix):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)

    torch = importlib.import_module("torch")
    numpy = importlib.import_module("numpy")
    yaml = importlib.import_module("yaml")
    importlib.import_module("placer")
    importlib.import_module("placer.ops.parser_txt.parser_txt_cpp")
    importlib.import_module("dreamplace.ops.place_io.place_io_cpp")
    importlib.import_module(
        "dreamplace.ops.timing_heterosta.timing_heterosta_cpp"
    )
    partitioner = importlib.import_module("partitioner")
    importlib.import_module("placer.d2d_placer")

    if int(numpy.__version__.split(".", 1)[0]) >= 2:
        raise RuntimeError(f"NumPy < 2 is required; found {numpy.__version__}")
    if torch.version.cuda is not None:
        raise RuntimeError(
            f"CPU-only PyTorch is required; found CUDA build {torch.version.cuda}"
        )
    if torch.cuda.is_available():
        raise RuntimeError("CPU-only D3D environment unexpectedly exposes CUDA")
    tensor_device = str(torch.ones(1).device)
    if tensor_device != "cpu":
        raise RuntimeError(
            f"D3D CPU smoke tensor was created on unexpected device {tensor_device}"
        )
    checked_extensions = check_cpu_only_linkage(prefix)

    pinned_source_revision = source_revision(Path(__file__).resolve().parents[1])
    manifest_path = prefix / ".taiwei-d3d-install.json"
    if manifest_path.exists() and not args.write_manifest:
        installed = json.loads(manifest_path.read_text(encoding="utf-8"))
        installed_revision = installed.get("source_revision")
        if pinned_source_revision and installed_revision != pinned_source_revision:
            raise RuntimeError(
                "installed source revision does not match the pinned checkout: "
                f"{installed_revision!r} != {pinned_source_revision!r}; "
                "reinstall the tool"
            )
    elif args.require_manifest and not args.write_manifest:
        raise RuntimeError(
            f"install manifest is missing: {manifest_path}; reinstall the tool"
        )

    payload = {
        "schema": "orfs.d3d-partition.install",
        "schema_version": 1,
        "install_prefix": str(prefix),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "device_mode": "cpu",
        "smoke_tensor_device": tensor_device,
        "cpu_linkage_checked_extensions": checked_extensions,
        "numpy": numpy.__version__,
        "pyyaml": yaml.__version__,
        "partitioner_module": str(Path(partitioner.__file__).resolve()),
        "source_revision": pinned_source_revision,
    }
    if args.write_manifest:
        atomic_write(
            prefix / ".taiwei-d3d-install.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
    print(json.dumps(payload, sort_keys=True))
    print("D3D_INSTALL_CHECK_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"error: {error}")
