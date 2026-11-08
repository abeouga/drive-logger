# -*- coding: utf-8 -*-
"""約束の定義そのものの検査と、firmware のソースとの突き合わせ。

- 定義が正しい JSON Schema（Draft 2020-12）か、どの定義にも版があるか
- 見本（examples/）が定義に合うか
- firmware のソースの定数（送るファイル・止まる速さ・CSV の列・出来事の種類・送る走行の決まり）が定義と同じか
  （firmware にはテストの仕組みが無いので、ここでソースを読んで比べる）

使うのは標準ライブラリと jsonschema・pytest だけ（pipeline・api の環境に依存しない）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parents[1]
FIRMWARE = CONTRACTS.parent / "firmware" / "ct125_logger"


def load(relative: str) -> dict:
    return json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))


def schema_paths() -> list[Path]:
    return sorted(CONTRACTS.glob("*/*.schema.json"))


def registry() -> Registry:
    resources = []
    for path in schema_paths():
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def validator(relative: str) -> Draft202012Validator:
    return Draft202012Validator(load(relative), registry=registry(), format_checker=FormatChecker())


# ------------------------------------------------------------------ 定義そのもの
@pytest.mark.parametrize("path", schema_paths(), ids=lambda p: p.relative_to(CONTRACTS).as_posix())
def test_schema_is_valid_draft_2020_12(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith("/contracts/" + path.relative_to(CONTRACTS).as_posix())


@pytest.mark.parametrize("path", sorted(CONTRACTS.glob("**/*.json")), ids=lambda p: p.relative_to(CONTRACTS).as_posix())
def test_every_definition_has_a_version(path):
    if "examples" in path.parts:
        return
    assert isinstance(json.loads(path.read_text(encoding="utf-8")).get("version"), int)


@pytest.mark.parametrize("path", sorted(CONTRACTS.glob("sd/*.table.json")), ids=lambda p: p.name)
def test_table_schema_fields(path):
    table = json.loads(path.read_text(encoding="utf-8"))
    names = [field["name"] for field in table["fields"]]
    assert len(names) == len(set(names))
    assert all(field["type"] in {"integer", "number", "string", "boolean"} for field in table["fields"])


def test_session_definitions_exist():
    session = load("sd/session.json")
    for item in session["files"] + session["root_files"]:
        if "definition" in item:
            assert (CONTRACTS / "sd" / item["definition"]).exists(), item
    upload = load("upload/upload.json")
    sent = {item["name"] for item in session["files"] if item["send"]}
    assert sent == set(upload["files"]["allowed"])
    assert {item["name"] for item in session["files"] if item["required"]} == set(upload["files"]["required"])
    assert set(session["memo_files"]) <= sent


def test_request_schema_lists_the_allowed_files():
    upload = load("upload/upload.json")
    request = load("upload/start_request.schema.json")
    assert request["properties"]["files"]["items"]["properties"]["name"]["enum"] == upload["files"]["allowed"]
    assert request["properties"]["files"]["items"]["properties"]["size"]["maximum"] == upload["files"]["max_bytes"]


def test_patterns_agree_with_common():
    common = load("common.json")
    request = load("upload/start_request.schema.json")
    response = load("upload/start_response.schema.json")
    session = load("upload/upload_session.schema.json")
    assert request["properties"]["ride_id"]["pattern"] == common["ride_id"]["pattern"]
    assert response["properties"]["ride_id"]["pattern"] == common["ride_id"]["pattern"]
    assert session["properties"]["ride_id"]["pattern"] == common["ride_id"]["pattern"]
    assert request["properties"]["local_session"]["pattern"] == common["local_session"]["pattern"]
    assert session["properties"]["device_id"]["pattern"] == common["device_id"]["pattern"]


# ------------------------------------------------------------------ 見本
EXAMPLES = {
    "examples/app/rides.json": "app/rides.schema.json",
    "examples/app/ride.json": "app/ride.schema.json",
    "examples/app/spec.json": "app/spec.schema.json",
    "examples/app/wave.json": "app/wave.schema.json",
    "examples/records/ledger.json": "records/ledger.schema.json",
    "examples/records/run.json": "records/run.schema.json",
    "examples/records/model.json": "records/model.schema.json",
    "examples/upload/start_request.json": "upload/start_request.schema.json",
    "examples/upload/start_response.json": "upload/start_response.schema.json",
    "examples/upload/complete_response.json": "upload/complete_response.schema.json",
    "examples/upload/upload_complete.json": "upload/upload_complete.schema.json",
}


@pytest.mark.parametrize("example, schema", EXAMPLES.items())
def test_example_matches_its_schema(example, schema):
    validator(schema).validate(load(example))


def test_every_example_is_checked():
    examples = {p.relative_to(CONTRACTS).as_posix() for p in CONTRACTS.glob("examples/**/*.json")}
    assert examples == set(EXAMPLES)


def test_ride_columns_have_the_same_length():
    ride = load("examples/app/ride.json")
    lengths = {name: len(values) for name, values in ride["columns"].items() if values is not None}
    assert set(lengths.values()) == {ride["n"]}


# ------------------------------------------------------------------ firmware のソース
def firmware_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(FIRMWARE.glob("*.ino")) + sorted(FIRMWARE.glob("*.cpp")))


def string_array(source: str, name: str) -> list[str]:
    match = re.search(rf"{name}\[\]\s*=\s*\{{([^}}]*)\}}", source)
    assert match, f"{name} が見つかりません"
    return re.findall(r'"([^"]+)"', match.group(1))


def test_firmware_sends_only_allowed_files():
    upload = load("upload/upload.json")
    send = string_array(firmware_source(), "SEND_FILES")
    assert set(send) <= set(upload["files"]["allowed"])
    assert set(upload["files"]["required"]) <= set(send)
    assert "notes.md" in send


def test_firmware_stop_speed_matches_common():
    match = re.search(r"STOP_SPEED_KMH\s*=\s*([0-9.]+)f?;", firmware_source())
    assert match and float(match.group(1)) == load("common.json")["stop_speed_kmh"]["value"]


def test_firmware_csv_headers_match_tables():
    source = firmware_source()
    headers = {}
    for name, header in re.findall(r'openCsv\("([a-z_]+)\.csv",\s*((?:"[^"]*"\s*)+)\)', source):
        headers[name] = "".join(re.findall(r'"([^"]*)"', header)).split(",")
    for name in ("accel", "events", "status"):
        assert headers[name] == [f["name"] for f in load(f"sd/{name}.table.json")["fields"]], name
    gps = load("sd/gps.table.json")
    gps_headers = re.findall(r'"(t_rx_us,utc,[a-z_,]+)"', source)
    expected = [f["name"] for f in gps["fields"]]
    assert sorted(h.split(",") for h in gps_headers) == sorted([expected, expected + [f["name"] for f in gps["optional_fields"]]])


def test_firmware_event_types_match_table():
    source = firmware_source()
    written = set(re.findall(r'logEvent\("([a-z_]+)"', source)) | set(re.findall(r'"(gps_valid|gps_lost)"', source))
    allowed = load("sd/events.table.json")["fields"][1]["constraints"]["enum"]
    assert written == set(allowed)


def test_firmware_upload_rules_match():
    source = firmware_source()
    rules = load("upload/upload.json")["device_rules"]
    prefix = re.search(r'UPLOADABLE_FIRMWARE = "\\"firmware\\": \\"([A-Z0-9_]+)";', source)
    assert prefix and prefix.group(1) == rules["firmware_prefix"]
    size = re.search(r"MIN_ACCEL_BYTES = ([0-9]+) \* ([0-9]+);", source)
    assert size and int(size.group(1)) * int(size.group(2)) == rules["min_accel_bytes"]
    version = re.search(r'#define FW_VERSION "([^"]+)"', source)
    assert version and re.fullmatch(load("sd/meta.schema.json")["properties"]["firmware"]["pattern"], version.group(1))
    assert version.group(1).startswith(rules["firmware_prefix"])


def test_firmware_state_files_match_session():
    source = firmware_source()
    session = load("sd/session.json")
    names = {item["name"] for item in session["files"]} | {item["name"] for item in session["root_files"]}
    for constant in ("UPLOADED_FILE", "STATE_FILE", "LOG_FILE"):
        match = re.search(rf'{constant} = "([^"]+)";', source)
        assert match and match.group(1) in names, constant


def test_firmware_uses_the_upload_paths_and_auth():
    source = firmware_source()
    upload = load("upload/upload.json")
    start = next(step for step in upload["steps"] if step["name"] == "start")
    complete = next(step for step in upload["steps"] if step["name"] == "complete")
    assert f'"{start["path"]}"' in source
    prefix, suffix = complete["path"].split("{ride_id}")
    assert f'"{prefix}" + ticket.rideId + "{suffix}"' in source
    assert f'"{upload["auth"]["scheme"]} "' in source
    for key in ("local_session", "files", "name", "size", "ride_id"):
        assert f'\\"{key}\\"' in source, key
