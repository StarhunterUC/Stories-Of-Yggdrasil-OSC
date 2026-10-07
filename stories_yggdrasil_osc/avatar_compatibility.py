from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MIN_UNITY_PROTOCOL = 20
MAX_UNITY_PROTOCOL = 20
RECOMMENDED_UNITY_TOOL = "0.5.10-TB17.1"

PARAM_PREFIX = "SoY_"
MARKER_FIELDS = {
    "SoY_UnityToolPresent": "present",
    "SoY_UnityToolMajor": "major",
    "SoY_UnityToolMinor": "minor",
    "SoY_UnityToolPatch": "patch",
    "SoY_UnityToolTB": "tb",
    "SoY_UnityToolTBRevision": "tb_revision",
    "SoY_ProtocolVersion": "protocol",
    "SoY_UnitySchemaValid": "schema_valid",
    "SoY_UnityMarkerBeacon": "beacon",
}
MARKER_PARAMETERS = frozenset(MARKER_FIELDS)

# Desktop -> avatar state/feedback parameters. Seeing these does not prove that
# the avatar contains a current Stories-generated gameplay schema.
OUTPUT_ONLY_PARAMETERS = frozenset(
    {
        "SoY_HPPercent",
        "SoY_MPPercent",
        "SoY_HPStage",
        "SoY_DamageReaction",
        "SoY_Damaged",
        "SoY_Healing",
        "SoY_CriticalHP",
        "SoY_KO",
        "SoY_Invulnerable",
        "SoY_Blocked",
        "SoY_BurnActive",
        "SoY_Silenced",
        "SoY_Frozen",
        "SoY_Bound",
        "SoY_Bleeding",
        "SoY_MagicLocked",
        "SoY_MovementLocked",
        "SoY_HealingRejected",
    }
)


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    try:
        return bool(int(float(value)))
    except (TypeError, ValueError):
        return bool(value)


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


@dataclass
class UnityAvatarCompatibility:
    """Track the Unity Tool build/protocol marker emitted by the loaded avatar.

    Direct Stories-generated SoY gameplay input fails closed unless Protocol 20
    and a valid TB17 schema marker are observed. Non-SoY external compatibility
    inputs remain available for avatars that do not use the Stories Unity Tool.
    """

    avatar_id: str = ""
    values: dict[str, Any] = field(default_factory=dict)
    saw_protected_input: bool = False
    _logged_blocks: set[str] = field(default_factory=set)

    def reset(self, avatar_id: str = "") -> None:
        self.avatar_id = str(avatar_id or "")
        self.values.clear()
        self.saw_protected_input = False
        self._logged_blocks.clear()

    @staticmethod
    def is_marker_parameter(name: str) -> bool:
        return str(name or "") in MARKER_PARAMETERS

    @staticmethod
    def is_output_only_parameter(name: str) -> bool:
        return str(name or "") in OUTPUT_ONLY_PARAMETERS

    @classmethod
    def is_protected_soy_parameter(cls, name: str) -> bool:
        parameter = str(name or "").strip()
        return bool(
            parameter.startswith(PARAM_PREFIX)
            and parameter not in MARKER_PARAMETERS
            and parameter not in OUTPUT_ONLY_PARAMETERS
        )

    def observe_parameter(self, name: str, value: Any) -> bool:
        field_name = MARKER_FIELDS.get(str(name or ""))
        if not field_name:
            return False
        if field_name in {"present", "schema_valid"}:
            self.values[field_name] = _as_bool(value)
        else:
            self.values[field_name] = _as_int(value)

        # TB17.1 periodically alternates an encoded local beacon between 117 and
        # 118. Seeing either value proves the current Tool/Protocol/schema tuple
        # even if Desktop started after VRChat had already emitted the static
        # marker parameters.
        if field_name == "beacon" and self.values[field_name] in {117, 118}:
            self.values.update(
                {
                    "present": True,
                    "major": 0,
                    "minor": 5,
                    "patch": 10,
                    "tb": 17,
                    "tb_revision": 1,
                    "protocol": 20,
                    "schema_valid": True,
                }
            )
            self._logged_blocks.clear()
        return True

    def note_protected_input(self) -> None:
        self.saw_protected_input = True

    @property
    def marker_complete(self) -> bool:
        return all(
            key in self.values
            for key in ("present", "major", "minor", "patch", "tb", "tb_revision", "protocol", "schema_valid")
        )

    @property
    def core_marker_complete(self) -> bool:
        # SoY_UnityToolPresent is retained as diagnostics/legacy marker data, but
        # VRChat can briefly emit its Bool default before the local parameter
        # driver publishes the marker state. The version/protocol/schema fields
        # are sufficient to prove a current TB17+ authored avatar.
        return all(
            key in self.values
            for key in ("major", "minor", "patch", "tb", "tb_revision", "protocol", "schema_valid")
        )

    @property
    def tool_version(self) -> str:
        if not any(key in self.values for key in ("major", "minor", "patch", "tb")):
            return "Unknown"
        major = _as_int(self.values.get("major"))
        minor = _as_int(self.values.get("minor"))
        patch = _as_int(self.values.get("patch"))
        tb = _as_int(self.values.get("tb"))
        revision = _as_int(self.values.get("tb_revision"))
        build = f"TB{tb}" if tb > 0 else ""
        if build and revision > 0:
            build += f".{revision}"
        suffix = f" {build}" if build else ""
        return f"v{major}.{minor}.{patch}{suffix}"

    @property
    def protocol(self) -> int | None:
        if "protocol" not in self.values:
            return None
        return _as_int(self.values.get("protocol"))

    @property
    def schema_valid(self) -> bool | None:
        if "schema_valid" not in self.values:
            return None
        return bool(self.values.get("schema_valid"))

    @property
    def status(self) -> str:
        protocol = self.protocol
        if protocol is not None and protocol > MAX_UNITY_PROTOCOL:
            return "update_required_desktop"
        if protocol is not None and protocol < MIN_UNITY_PROTOCOL:
            return "update_required_avatar"
        if self.schema_valid is False:
            return "schema_invalid"
        if self.core_marker_complete:
            tool_tb = _as_int(self.values.get("tb"))
            if protocol == MIN_UNITY_PROTOCOL and tool_tb >= 17 and self.schema_valid is True:
                return "compatible"
            return "update_required_avatar"
        if self.saw_protected_input:
            return "update_required_avatar"
        return "reading_marker"

    @property
    def compatible(self) -> bool:
        return self.status == "compatible"

    def block_reason(self) -> str:
        status = self.status
        if status == "update_required_desktop":
            return (
                f"Avatar uses OSC protocol {self.protocol}; this Desktop supports "
                f"{MIN_UNITY_PROTOCOL}-{MAX_UNITY_PROTOCOL}. Update the OSC Desktop."
            )
        if status == "schema_invalid":
            return (
                f"{self.tool_version} reported an invalid/outdated Stories avatar schema. "
                "Open the current Unity Tool and run Migrate / Validate Avatar."
            )
        if status == "update_required_avatar":
            if self.protocol is not None and self.protocol != MIN_UNITY_PROTOCOL:
                return (
                    f"Stories avatar protocol {self.protocol} is unsupported. Protocol "
                    f"{MIN_UNITY_PROTOCOL} is required; migrate/repair the avatar with {RECOMMENDED_UNITY_TOOL}."
                )
            if self.protocol == MIN_UNITY_PROTOCOL and not self.core_marker_complete:
                return (
                    f"Protocol {MIN_UNITY_PROTOCOL} was detected, but the Unity Tool marker is incomplete. "
                    f"Run Safe Repair All / Migrate & Validate with {RECOMMENDED_UNITY_TOOL}, then reload the avatar."
                )
            return (
                "Stories gameplay input arrived without a complete current Unity Tool compatibility marker. "
                f"Migrate/repair the avatar with {RECOMMENDED_UNITY_TOOL}."
            )
        return "Waiting for the Unity Tool compatibility marker."

    def block_notice_due(self, parameter: str) -> bool:
        key = f"{self.status}:{parameter}"
        if key in self._logged_blocks:
            return False
        self._logged_blocks.add(key)
        return True

    def ui_summary(self) -> str:
        status = self.status
        if status == "compatible":
            return f"Unity Tool: {self.tool_version} • Protocol {self.protocol} • Schema valid"
        if status == "update_required_desktop":
            return f"Unity Tool: {self.tool_version} • Protocol {self.protocol} • DESKTOP UPDATE REQUIRED"
        if status == "schema_invalid":
            return f"Unity Tool: {self.tool_version} • Protocol {self.protocol if self.protocol is not None else '—'} • MIGRATION REQUIRED"
        if status == "update_required_avatar":
            proto = self.protocol if self.protocol is not None else "Unknown"
            return f"Unity Tool: {self.tool_version} • Protocol {proto} • AVATAR UPDATE REQUIRED"
        return "Unity Tool: waiting for TB17.1 / Protocol 20 marker"

    def diagnostics_lines(self) -> list[str]:
        status_labels = {
            "compatible": "Supported",
            "reading_marker": "Waiting for marker",
            "update_required_avatar": "Avatar update required",
            "update_required_desktop": "Desktop update required",
            "schema_invalid": "Avatar migration/validation required",
        }
        return [
            f"Unity Tool: {self.tool_version}",
            f"Unity OSC protocol: {self.protocol if self.protocol is not None else 'unknown'} (supported {MIN_UNITY_PROTOCOL}-{MAX_UNITY_PROTOCOL})",
            f"Unity marker present flag: {self.values.get('present', 'unknown')}",
            f"Unity marker beacon: {self.values.get('beacon', 'unknown')}",
            f"Unity schema: {'valid' if self.schema_valid is True else 'invalid' if self.schema_valid is False else 'unknown'}",
            f"Unity compatibility: {status_labels.get(self.status, self.status)}",
        ]
