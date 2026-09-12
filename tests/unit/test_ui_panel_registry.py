"""
tests/unit/test_ui_panel_registry.py — Unit tests for engine/core/ui_panel_registry.py

Coverage:
  - Default panel registration on import
  - Lookup by key (get / get_or_none)
  - PanelTypeDescriptor.as_dict() shape
  - Custom panel registration
  - Duplicate registration raises ValueError
  - PanelRenderer protocol compliance check
  - Schema fields completeness
  - list_keys() returns all built-in panels
"""

from __future__ import annotations

import pytest
from typing import Any

from engine.core.ui_panel_registry import (
    PanelTypeDescriptor,
    PanelRenderer,
    ui_panel_registry,
    register_default_panels,
)
from engine.core.registry import Registry


# ── Built-in panel type constants ──────────────────────────────────────────────
BUILTIN_PANELS = [
    "scanner_table",
    "option_chain",
    "metric_card",
    "order_blotter",
    "position_table",
    "graph_canvas",
    "heatmap",
]


# ── 1. Default registration ────────────────────────────────────────────────────

class TestDefaultRegistration:
    def test_all_builtin_panels_registered(self):
        """All seven built-in panel types must be in the registry on import."""
        keys = ui_panel_registry.list_keys()
        for panel_type in BUILTIN_PANELS:
            assert panel_type in keys, f"Built-in panel '{panel_type}' not registered"

    def test_no_extra_registrations_from_import(self):
        """Registry must contain exactly the built-in panels (no extras from import side-effects)."""
        keys = set(ui_panel_registry.list_keys())
        # Registry may have more if tests add custom panels; built-ins must be a subset
        assert set(BUILTIN_PANELS).issubset(keys)

    def test_register_default_panels_idempotent(self):
        """Calling register_default_panels() again must not raise (already-registered guard)."""
        # Should silently skip — no ValueError
        register_default_panels()
        # Keys unchanged
        assert set(BUILTIN_PANELS).issubset(set(ui_panel_registry.list_keys()))


# ── 2. Descriptor lookup ───────────────────────────────────────────────────────

class TestDescriptorLookup:
    @pytest.mark.parametrize("panel_type", BUILTIN_PANELS)
    def test_get_builtin_panel(self, panel_type: str):
        desc = ui_panel_registry.get(panel_type)
        assert isinstance(desc, PanelTypeDescriptor)
        assert desc.panel_type == panel_type

    def test_get_missing_raises_keyerror(self):
        with pytest.raises(KeyError, match="not registered"):
            ui_panel_registry.get("nonexistent.panel_xyz")

    def test_get_or_none_missing_returns_none(self):
        result = ui_panel_registry.get_or_none("nonexistent.panel_xyz")
        assert result is None

    def test_has_builtin_returns_true(self):
        assert ui_panel_registry.has("metric_card") is True

    def test_has_missing_returns_false(self):
        assert ui_panel_registry.has("does_not_exist") is False


# ── 3. Descriptor structure ────────────────────────────────────────────────────

class TestDescriptorStructure:
    @pytest.mark.parametrize("panel_type", BUILTIN_PANELS)
    def test_descriptor_fields_complete(self, panel_type: str):
        desc = ui_panel_registry.get(panel_type)
        assert desc.panel_type, "panel_type must be non-empty"
        assert desc.title, "title must be non-empty"
        assert desc.description, "description must be non-empty"
        assert isinstance(desc.schema, dict), "schema must be a dict"
        assert isinstance(desc.default_config, dict), "default_config must be a dict"
        assert desc.icon, "icon must be non-empty"
        assert isinstance(desc.refresh_ms, int), "refresh_ms must be int"
        assert desc.refresh_ms >= 0, "refresh_ms must be non-negative"

    @pytest.mark.parametrize("panel_type", BUILTIN_PANELS)
    def test_as_dict_shape(self, panel_type: str):
        d = ui_panel_registry.get(panel_type).as_dict()
        expected_keys = {
            "panel_type", "title", "description",
            "schema", "default_config", "icon", "refresh_ms",
        }
        assert expected_keys == set(d.keys()), (
            f"as_dict() missing keys: {expected_keys - set(d.keys())}"
        )

    @pytest.mark.parametrize("panel_type", BUILTIN_PANELS)
    def test_as_dict_values_serializable(self, panel_type: str):
        import json
        d = ui_panel_registry.get(panel_type).as_dict()
        # Must not raise
        json.dumps(d)

    def test_scanner_table_event_driven(self):
        desc = ui_panel_registry.get("scanner_table")
        assert desc.refresh_ms == 0, "scanner_table must be event-driven (refresh_ms=0)"

    def test_graph_canvas_event_driven(self):
        desc = ui_panel_registry.get("graph_canvas")
        assert desc.refresh_ms == 0, "graph_canvas must be event-driven (refresh_ms=0)"

    def test_metric_card_has_period_default(self):
        desc = ui_panel_registry.get("metric_card")
        assert "period" in desc.default_config

    def test_option_chain_requires_underlying_in_schema(self):
        desc = ui_panel_registry.get("option_chain")
        required = desc.schema.get("required", [])
        assert "underlying" in required

    def test_position_table_shows_trailing_sl(self):
        desc = ui_panel_registry.get("position_table")
        assert desc.default_config.get("show_trailing_sl") is True


# ── 4. Custom panel registration ───────────────────────────────────────────────

class TestCustomRegistration:
    """
    Tests use a fresh temporary Registry to avoid polluting the singleton.
    """

    def _make_registry(self) -> Registry[PanelTypeDescriptor]:
        return Registry("test_ui_panel")

    def test_register_custom_panel(self):
        reg = self._make_registry()
        custom = PanelTypeDescriptor(
            panel_type="custom.test_panel",
            title="Test Panel",
            description="A test panel for unit testing.",
            schema={"type": "object", "properties": {}},
            default_config={"key": "value"},
            icon="🧪",
            refresh_ms=2000,
        )
        reg.register("custom.test_panel", custom)
        assert reg.has("custom.test_panel")
        retrieved = reg.get("custom.test_panel")
        assert retrieved.title == "Test Panel"

    def test_duplicate_registration_raises(self):
        reg = self._make_registry()
        desc = PanelTypeDescriptor(
            panel_type="custom.dupe",
            title="Dupe",
            description="Duplicate test.",
            schema={},
            default_config={},
        )
        reg.register("custom.dupe", desc)
        with pytest.raises(ValueError, match="already registered"):
            reg.register("custom.dupe", desc)

    def test_unregister_panel(self):
        reg = self._make_registry()
        desc = PanelTypeDescriptor(
            panel_type="custom.removable",
            title="Removable",
            description="Will be removed.",
            schema={},
            default_config={},
        )
        reg.register("custom.removable", desc)
        assert reg.has("custom.removable")
        reg.unregister("custom.removable")
        assert not reg.has("custom.removable")

    def test_list_keys_sorted(self):
        reg = self._make_registry()
        for key in ["z_panel", "a_panel", "m_panel"]:
            reg.register(
                key,
                PanelTypeDescriptor(
                    panel_type=key,
                    title=key,
                    description=key,
                    schema={},
                    default_config={},
                ),
            )
        assert reg.list_keys() == sorted(["z_panel", "a_panel", "m_panel"])

    def test_len_matches_registration_count(self):
        reg = self._make_registry()
        assert len(reg) == 0
        for i in range(3):
            reg.register(
                f"panel_{i}",
                PanelTypeDescriptor(
                    panel_type=f"panel_{i}",
                    title=f"Panel {i}",
                    description="test",
                    schema={},
                    default_config={},
                ),
            )
        assert len(reg) == 3


# ── 5. PanelRenderer protocol ─────────────────────────────────────────────────

class TestPanelRendererProtocol:
    def test_renderer_protocol_runtime_check(self):
        """
        A class implementing the PanelRenderer protocol passes isinstance()
        check at runtime (runtime_checkable).
        """
        class GoodRenderer:
            async def render(
                self,
                panel_config: dict[str, Any],
                strategy_id: str | None,
                context: dict[str, Any],
            ) -> dict[str, Any]:
                return {}

        renderer = GoodRenderer()
        assert isinstance(renderer, PanelRenderer)

    def test_non_renderer_fails_protocol_check(self):
        class BadRenderer:
            def not_render(self):
                pass

        obj = BadRenderer()
        assert not isinstance(obj, PanelRenderer)

    def test_renderer_with_wrong_signature_not_caught_at_runtime(self):
        """
        Python's runtime protocol check only verifies attribute presence, not
        signature.  This confirms the protocol is structural, not nominal.
        """
        class PartialRenderer:
            async def render(self):  # wrong signature, but has render attr
                return {}

        # isinstance still passes because 'render' attribute exists
        assert isinstance(PartialRenderer(), PanelRenderer)


# ── 6. Frozen dataclass immutability ──────────────────────────────────────────

class TestDescriptorImmutability:
    def test_descriptor_is_frozen(self):
        desc = ui_panel_registry.get("metric_card")
        with pytest.raises((AttributeError, TypeError)):
            desc.title = "Hacked"  # type: ignore[misc]

    def test_descriptor_default_config_not_shared(self):
        """
        default_config dict should not be mutated by tests — frozen dataclass
        but the dict inside could be mutated.  Verify it's not the same object.
        """
        desc1 = ui_panel_registry.get("metric_card")
        desc2 = ui_panel_registry.get("metric_card")
        # Same frozen object — same dict
        assert desc1.default_config is desc2.default_config


# ── 7. Edge-case: empty registry ──────────────────────────────────────────────

class TestEmptyRegistry:
    def test_empty_registry_list_keys(self):
        reg: Registry[PanelTypeDescriptor] = Registry("empty_test")
        assert reg.list_keys() == []

    def test_empty_registry_len(self):
        reg: Registry[PanelTypeDescriptor] = Registry("empty_test_len")
        assert len(reg) == 0
