from __future__ import annotations

import json
from pathlib import Path

from stories_yggdrasil_osc import __version__

ROOT = Path(__file__).resolve().parent
metadata = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))

expected = str(metadata.get("version") or "").strip()
if not expected:
    raise SystemExit("version.json is missing a version.")
if __version__ != expected:
    raise SystemExit(f"Package version mismatch: {__version__!r} != {expected!r}")
if str(metadata.get("channel") or "") == "pre-build" and "prebuild" not in expected:
    raise SystemExit("Pre-build channel versions must include 'prebuild'.")
if str(metadata.get("api_recommended")) != "0.8.19":
    raise SystemExit("Protocol 21 pre-build must recommend OSC API 0.8.19")
if not (ROOT / "Stories Of Yggdrasil OSC.spec").is_file():
    raise SystemExit("PyInstaller spec file is missing.")
if not (ROOT / "assets" / "stories_osc_icon.ico").is_file():
    raise SystemExit("Application icon is missing.")

required_markers = {
    "main.py": ["app_v0814", "configure_tls_runtime"],
    "stories_yggdrasil_osc/tls_runtime.py": [
        "Windows Trust Store (truststore)",
        "ssl.CERT_REQUIRED",
        "TLSv1_2",
        "certifi.where()",
    ],
    "stories_yggdrasil_osc/app_v0814.py": [
        "Reconnect All",
        "Quick Actions",
        "Create Support Bundle",
        "Incoming Contact Attribution",
        "combat_npc_source_combo",
        "combat_pvp_source_combo",
        "Enable NPC Mode",
        "Runtime Profile: NPC",
        "def enable_npc_mode",
    ],
    "stories_yggdrasil_osc/qol.py": [
        "build_action_catalog",
        "append_grouped_activity",
        "create_support_bundle",
        "redact_sensitive",
        "should_suppress_activity_repeat",
    ],
    "stories_yggdrasil_osc/config.py": [
        '"version": 21',
        '"external_damage_source": "SoY_ExternalDamageSource"',
        '"window_geometry"',
        '"action_favorites"',
        '"npc_favorites"',
        '"combat_authority"',
        '"vrchat_identity"',
        '"unclassified_contacts_are_enemy": True',
    ],
    "contracts/OSC_CONTRACT_v15.json": ["verified_attacker_identity"],
    "contracts/OSC_CONTRACT_v16.json": ["pairing_persists_through_transport_outage", "full_state_refresh_after_reconnect"],
    "contracts/OSC_CONTRACT_v17.json": ["revision_epoch_rebase_after_sam_restart", "maintenance_html_redirect_detected_as_transport_failure"],
    "contracts/OSC_CONTRACT_v18.json": [
        '"combat_event_endpoint": true',
        '"idempotent_contact_event_id": true',
        '"guess_remote_player_identity": false',
        '"player_to_npc_legacy_verified_route_preserved": true',
    ],
    "stories_yggdrasil_osc/combat_authority.py": [
        "class CombatCatalog",
        "class CombatSourceHint",
        "def build_incoming_contact_event",
        "def new_event_id",
    ],
    "stories_yggdrasil_osc/sam_client.py": [
        '"connection_state": "reconnecting"',
        "max_backoff = min(15.0, configured_backoff)",
        "def _poll_path(self)",
        "def _revision_epoch_rolled_back(self",
        "def _emit_poll_heartbeat(self",
        "redirected outside its API endpoint",
        '"/combat/catalog"',
        '"/combat/event"',
        "context=get_ssl_context()",
        "winhttp_request",
        "Windows WinHTTP/Schannel",
        '"/helpful-item/self"',
        '"/helpful-item/attempt"',
        '"/helpful-item/receipt"',
        '"/pvp/attempt"',
        '"/pvp/receipt"',
        "def pvp_attack_attempt",
        "def pvp_hit_receipt",
    ],
    "stories_yggdrasil_osc/avatar_compatibility.py": [
        "MIN_UNITY_PROTOCOL = 20",
        "MAX_UNITY_PROTOCOL = 21",
        'RECOMMENDED_UNITY_TOOL = "0.5.10-TB18"',
        "SoY_UnitySchemaValid",
        "SoY_UnityMarkerBeacon",
    ],
    "stories_yggdrasil_osc/app.py": [
        "sam_pending_remote_state",
        'source == "poll"',
        "def _submit_authoritative_contact",
        '"/soy/combat/source/vrchat_user_id"',
        'payload["vrchat_user_id"]',
        "self.sam_client.combat_event(payload)",
        "canonical_soy_contact",
        "external_damage_source",
        "avatar_compatibility",
        "combat_catalog_activity_signature",
        "def _submit_helpful_item_touch",
        "def _submit_helpful_item_receipt",
        "def _submit_pvp_attack_attempt",
        "pvp_hit_receipt",
        "protocol21_handshake",
        "is_physical_helpful_item",
    ],
    "stories_yggdrasil_osc/controller.py": [
        "_authoritative_contact_iframe_until",
        "_external_damage_source_latched_until",
        '"external_damage_source": False',
        '"reason": "contact_iframe"',
        '"helpful_item_received_type"',
        '"helpful_item_touch"',
        '"helpful_item_received"',
        '"pvp_attack_attempt"',
        '"SoY_PvPAttemptAverage"',
    ],
    "stories_yggdrasil_osc/helpful_items.py": [
        "HELPFUL_ITEM_ID_TO_NAME",
        "ITEM_RESULT_NO_ITEM",
        "ITEM_RESULT_EXPIRED",
    ],
    "contracts/OSC_CONTRACT_v21.json": [
        '"protocol": 21',
        '"physical_helpful_items": true',
        '"ambiguous_matches_fail_closed": true',
    ],
    "tests/test_helpful_items_protocol21.py": [
        "test_self_head_touch_uses_selected_helpful_item",
        "test_other_head_touch_is_rising_edge_only",
        "test_head_receiver_bus_reconstructs_item_id",
    ],
    "stories_yggdrasil_osc/update_manager.py": [
        "context=get_ssl_context()",
        "Test Builds",
        "_select_release",
        "0.8.21-prebuild.4 < 0.8.21 < 0.8.22-prebuild.1",
    ],
    "requirements.txt": [
        "truststore>=0.10,<1",
        "certifi>=2025.1.31",
    ],
    "Stories Of Yggdrasil OSC.spec": [
        "collect_submodules(\"truststore\")",
    ],
    "BUILD_AND_PACKAGE_v0.8.20.ps1": [
        "Remove-Item -Recurse -Force build, dist, release",
        "Stories_Of_Yggdrasil_OSC_Windows_v0.8.20.zip",
    ],
    ".github/workflows/release.yml": [
        "Remove-Item -Recurse -Force build, dist",
    ],
    "tests/test_tls_runtime_v0819.py": [
        "test_context_never_disables_certificate_verification",
        "test_sam_client_passes_hardened_context_to_urllib",
    ],
    "stories_yggdrasil_osc/winhttp_transport.py": [
        "WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY",
        "WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2",
        "WINHTTP_DISABLE_REDIRECTS",
        "Windows WinHTTP/Schannel",
    ],
    "tests/test_winhttp_transport_v0820.py": [
        "test_windows_native_transport_is_preferred_for_sam",
        "test_native_certificate_error_is_not_bypassed",
        "test_native_redirect_is_refused",
    ],
    "tests/test_combat_authority_v0818.py": [
        "test_npc_to_player_uses_server_bound_avatar_and_never_sends_power",
        "test_unattributed_player_contact_is_refused_instead_of_guessed",
        "test_sam_client_combat_event_keeps_same_id_across_transient_retry",
        "test_authoritative_contact_iframe_blocks_repeat_before_server_roundtrip",
    ],
    "tests/test_prebuild_0821.py": [
        "test_canonical_friendly_contact_is_not_reclassified_as_npc",
        "test_external_unclassified_contact_keeps_enemy_fallback",
        "test_protocol20_external_source_is_not_treated_as_canonical_friendly",
        "test_enable_npc_mode_commits_runtime_switch_without_attacker",
    ],
    "tests/test_unity_marker_v0821.py": [
        "test_current_tb17_protocol20_marker_is_compatible",
        "test_protocol19_requires_tb17_migration",
        "test_protocol20_external_source_parameter_is_protected",
        "test_protocol20_marker_tolerates_present_false_startup_race",
        "test_protocol20_incomplete_marker_reports_incomplete_not_unsupported",
        "test_tb17_1_beacon_recovers_late_desktop_start",
        "test_tb17_1_beacon_alternates_without_losing_compatibility",
        "test_unknown_beacon_value_does_not_bypass_fail_closed",
    ],
}
for relative, markers in required_markers.items():
    text = (ROOT / relative).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"Missing Protocol 21 marker {marker!r} in {relative}")

print("Stories Of Yggdrasil OSC Desktop source audit passed.")
print(f"Desktop version: {expected}")
print(f"OSC API minimum: {metadata.get('api_minimum')}")
print(f"OSC API recommended: {metadata.get('api_recommended')}")
print(f"Unity Tool: {metadata.get('unity_tool')}")
print(f"{expected} preserves existing combat authority, adds Protocol 21 helpful-item handshakes, and keeps Sam.py HTTPS on native Windows WinHTTP/Schannel with certificate verification required.")
