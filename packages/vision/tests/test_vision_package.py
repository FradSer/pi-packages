from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"


def read_source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["extensions"] == ["./src/index.ts"]
    assert manifest["peerDependencies"]["@earendil-works/pi-coding-agent"] == "*"
    assert manifest["peerDependencies"]["@earendil-works/pi-ai"] == "*"


def test_feature_file_exists() -> None:
    feature = PACKAGE / "features" / "image-bridge.feature"
    assert feature.is_file()
    content = feature.read_text(encoding="utf-8")
    assert "removes the original images" in content
    assert "multimodal main model" in content


def test_extension_registers_image_bridge_and_configuration_command() -> None:
    source = read_source("index.ts")
    assert 'pi.on("input"' in source
    assert 'pi.registerCommand("vision"' in source
    assert 'ctx.modelRegistry.find' in source
    assert "describeImages" in (SRC / "bridge.ts").read_text(encoding="utf-8")
    assert 'action: "transform"' in source
    assert 'ctx.ui.select' in source
    assert 'ctx.ui.input' in source
    assert 'ctx.ui.confirm' in source


def test_bridge_only_handles_images_for_text_only_models() -> None:
    source = read_source("index.ts")
    assert 'ctx.model.input.includes("image")' in source
    assert "event.images" in source
    assert "images: []" in source
    assert "imageModels" in source
    assert 'model.input.includes("image")' in source
    assert "scopedModels" in source
    assert "getAvailable" in source
    assert 'vision · not configured' not in source


def test_prompt_mentions_images_and_instruction() -> None:
    source = read_source("index.ts")
    bridge = (SRC / "bridge.ts").read_text(encoding="utf-8")
    assert "visual context" in bridge
    assert "original image" in bridge
    assert "vision model" in bridge


def test_vision_request_uses_pi_model_registry_auth() -> None:
    source = read_source("bridge.ts")
    assert "getApiKeyAndHeaders" in source
    assert "registry.complete" in source
    assert "ImageContent" in source


def test_configuration_is_persisted_outside_the_session() -> None:
    source = read_source("config.ts")
    assert '"vision.json"' in source
    assert "writeFile" in source
    assert "readFile" in source
