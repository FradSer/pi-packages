from __future__ import annotations

import binascii
import json
import os
import struct
import subprocess
import zlib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"


def read_source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def write_test_png(path: Path, width: int = 32, height: int = 32) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + b"\x33\x66\x99" * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def run_input_harness(
    tmp_path: Path,
    text: str,
    image_data: str | None = None,
    main_model: str = "text-only",
) -> dict[str, object]:
    agent_dir = tmp_path / "agent"
    env = {
        **os.environ,
        "PI_CODING_AGENT_DIR": str(agent_dir),
        "VISION_TEST_MAIN_MODEL": main_model,
    }
    args = [
        "npx",
        "tsx",
        str(PACKAGE / "tests" / "vision_input_harness.ts"),
        text,
    ]
    if image_data is not None:
        args.append(image_data)
    completed = subprocess.run(
        args,
        cwd=PACKAGE.parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["extensions"] == ["./src/index.ts"]
    assert manifest["peerDependencies"]["@earendil-works/pi-coding-agent"] == "*"
    assert manifest["peerDependencies"]["@earendil-works/pi-ai"] == "*"


def test_native_image_attachment_is_intercepted_end_to_end(tmp_path: Path) -> None:
    original = '<file name="/tmp/native-image.png"></file>\nExplain the image'
    result = run_input_harness(tmp_path, original, "iVBORw0KGgo=")
    assert result["visionCallCount"] == 1
    assert result["visionImageCount"] == 1
    assert result["sessionUserImageCount"] == 1  # original image remains on the persisted user message
    assert result["sessionUserPrompt"] == original
    assert result["visionCallsAtUserMessageEnd"] == 0  # user message rendered before analysis starts
    assert "custom_message" not in result["sessionEntryTypes"]
    assert result["mainImageCount"] == 0  # only the provider-bound context has images removed
    assert "<image-analysis>" in str(result["mainPrompt"])
    assert "VISION_RESULT" in str(result["mainPrompt"])
    assert "<file" not in str(result["visionPrompt"])


def test_multimodal_main_model_receives_native_attachment_unchanged(tmp_path: Path) -> None:
    result = run_input_harness(
        tmp_path,
        "Explain the image",
        "iVBORw0KGgo=",
        main_model="multimodal",
    )
    assert result["visionCallCount"] == 0
    assert result["sessionUserImageCount"] == 1
    assert result["sessionUserPrompt"] == "Explain the image"
    assert result["mainImageCount"] == 1
    assert result["mainPrompt"] == "Explain the image"


def test_tui_pasted_image_path_is_intercepted_end_to_end(tmp_path: Path) -> None:
    image_path = tmp_path / "pi clipboard test.png"
    write_test_png(image_path)
    original = f"Explain this screenshot\n{image_path}"
    result = run_input_harness(tmp_path, original)
    assert result["visionCallCount"] == 1
    assert result["visionImageCount"] == 1
    assert result["sessionUserImageCount"] == 1  # image from the pasted path remains on the persisted user message
    assert "custom_message" not in result["sessionEntryTypes"]
    assert str(image_path) not in str(result["visionPrompt"])
    assert result["sessionUserPrompt"] == original
    assert result["mainImageCount"] == 0
    assert "<image-analysis>" in str(result["mainPrompt"])
    assert "VISION_RESULT" in str(result["mainPrompt"])


def test_feature_file_exists() -> None:
    feature = PACKAGE / "features" / "image-bridge.feature"
    assert feature.is_file()
    content = feature.read_text(encoding="utf-8")
    assert "preserves the complete original prompt" in content
    assert "does not replace, remove, rewrite, or add an internal message" in content
    assert "transient provider context" in content
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
    assert 'ctx.model.input ?? ["text"]' in source
    assert 'ctx.model.input ?? ["text"]' in source
    assert "event.images" in source
    assert "images," in source
    assert "analysisFor" in source
    assert 'pi.on("context"' in source
    assert 'return { action: "transform", text: event.text, images }' in source
    assert "imageModels" in source
    assert 'model.input.includes("image")' in source
    assert "scopedModels" in source
    assert "getAvailable" in source
    assert 'vision · not configured' not in source
    assert 'ctx.ui.setStatus("vision", undefined)' in source
    assert '`${config.enabled ? "vision"' not in source
    assert 'setWorkingIndicator' in source


def test_prompt_mentions_images_and_instruction() -> None:
    source = read_source("index.ts")
    bridge = (SRC / "bridge.ts").read_text(encoding="utf-8")
    assert "<image-analysis>" in bridge


def test_vision_request_uses_pi_model_registry_auth() -> None:
    source = read_source("bridge.ts")
    assert "getApiKeyAndHeaders" in source
    assert "registry.complete" in source
    assert "ImageContent" in source
    assert "ThinkingContent" in source


def test_configuration_is_persisted_outside_the_session() -> None:
    source = read_source("config.ts")
    assert '"vision.json"' in source
    assert "writeFile" in source
    assert "readFile" in source


def test_all_runtime_prompts_and_ui_copy_are_english() -> None:
    import re

    cjk = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
    offenders: list[str] = []
    for path in sorted(SRC.glob("*.ts")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if cjk.search(line):
                offenders.append(f"{path.name}:{line_number}: {line.strip()}")
    assert not offenders, "Non-English runtime copy found:\n" + "\n".join(offenders)
