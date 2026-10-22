"""Angle conventions, bounded reflection and presentation-only control behaviour."""

from dataclasses import FrozenInstanceError, astuple
from random import Random

import pygame
import pytest

from chromatophore_simulator import app
from chromatophore_simulator.dynamics import DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField
from chromatophore_simulator.reflection import (
    ANGLE_PRESETS,
    ReflectionSettings,
    reflection_responses,
)
from chromatophore_simulator.view import (
    FIELD_RECT,
    IRIDOPHORE_COLOUR,
    IRIDOPHORE_PATCHES,
    IRIDOPHORE_STRENGTH,
    SKIN_COLOUR,
    WINDOW_SIZE,
    FieldView,
    ReflectionAction,
    ViewMode,
    iridophore_base,
)


@pytest.mark.parametrize("angle", [-61, 61, float("nan"), float("inf"), True, "30"])
def test_invalid_angles_are_rejected(angle: float) -> None:
    """Both light and camera use the same validated degree range.

    :param angle: Unsupported angle value.
    """
    with pytest.raises(ValueError):
        ReflectionSettings(angle, 0)
    with pytest.raises(ValueError):
        ReflectionSettings(0, angle)


def test_reference_response_preserves_previous_palette() -> None:
    """Straight-on viewing and lighting reproduce the existing backing colours."""
    from math import exp

    responses = reflection_responses()
    assert all(response.colour == IRIDOPHORE_COLOUR for response in responses)
    assert all(response.strength == pytest.approx(1) for response in responses)
    for x, y in ((0, 0), (0.24, 0.3), (0.76, 0.36), (0.48, 0.78), (0.5, 0.5), (1, 1)):
        patch = max(
            exp(-2 * (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2))
            for cx, cy, rx, ry in IRIDOPHORE_PATCHES
        )
        previous = tuple(
            round(base + IRIDOPHORE_STRENGTH * patch * (colour - base))
            for base, colour in zip(SKIN_COLOUR, IRIDOPHORE_COLOUR, strict=True)
        )
        assert iridophore_base(x, y, responses) == previous


def test_angular_responses_are_bounded_fixed_and_smooth() -> None:
    """Supported angles stay finite; tiny changes do not cause abrupt colour jumps."""
    for view in ANGLE_PRESETS:
        for light in ANGLE_PRESETS:
            settings = ReflectionSettings(view, light)
            responses = reflection_responses(settings)
            assert responses == reflection_responses(settings)
            assert all(0 <= response.strength <= 1.3 for response in responses)
            assert all(0 <= value <= 255 for response in responses for value in response.colour)
    settings = ReflectionSettings()
    with pytest.raises(FrozenInstanceError):
        settings.view_angle = 30
    before, after = (
        reflection_responses(ReflectionSettings(30, 0)),
        reflection_responses(ReflectionSettings(30.001, 0)),
    )
    for first, second in zip(before, after, strict=True):
        assert abs(first.strength - second.strength) < 0.001
        assert all(abs(a - b) < 0.01 for a, b in zip(first.colour, second.colour, strict=True))


def test_tilting_blue_shifts_and_selects_different_patch_orientations() -> None:
    """Oblique reflection shifts towards blue and follows preferred patch normals."""
    front = reflection_responses()
    tilted = reflection_responses(ReflectionSettings(60, 0))
    assert tilted[1].colour[2] / tilted[1].colour[1] > front[1].colour[2] / front[1].colour[1]
    assert tilted[1].strength < front[1].strength
    right = reflection_responses(ReflectionSettings(30, 0))
    left = reflection_responses(ReflectionSettings(-30, 0))
    assert right[2].strength > right[0].strength
    assert left[0].strength > left[2].strength
    assert reflection_responses(ReflectionSettings(0, 30)) != front
    invisible = reflection_responses(ReflectionSettings(60, -60))
    assert all(response.strength == 0 for response in invisible)
    assert iridophore_base(0.24, 0.3, invisible) == SKIN_COLOUR


@pytest.mark.parametrize("use_mouse", [False, True])
def test_angle_controls_change_only_presentation(
    use_mouse: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Controls change Skin View while preserving held/dynamic state and disc geometry.

    :param use_mouse: Exercise buttons instead of A/I/O shortcuts.
    :param monkeypatch: Select a headless SDL driver for deterministic rendering.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    pygame.font.init()
    try:
        pygame.display.set_mode((1, 1))
        view = FieldView(pygame.Surface(WINDOW_SIZE))
        field = ChromatophoreField()
        field.start_dynamic(DynamicDisplay.TRAVELLING_WAVE)
        field.update(0.2)
        before = tuple(astuple(cell) for cell in field.cells)
        phase = field.dynamic.phase_seconds
        view.draw(field, 60)
        detailed = pygame.image.tobytes(view.surface.subsurface(FIELD_RECT), "RGB")
        source = Random(42)
        random_state = source.getstate()
        for command, key in (
            (ReflectionAction.VIEW, pygame.K_a),
            (ReflectionAction.LIGHT, pygame.K_i),
        ):
            button = next(button for button in view.reflection_buttons if button.command is command)
            event = (
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rectangle.center)
                if use_mouse
                else pygame.event.Event(pygame.KEYDOWN, key=key)
            )
            assert app.handle_event(event, field, view, source)
        assert view.reflection == ReflectionSettings(15, 15)
        view.draw(field, 60)
        assert pygame.image.tobytes(view.surface.subsurface(FIELD_RECT), "RGB") == detailed
        view.mode = ViewMode.SKIN
        view.reflection = ReflectionSettings()
        view.draw(field, 60)
        normal = pygame.image.tobytes(view.surface.subsurface(FIELD_RECT), "RGB")
        view.reflection = ReflectionSettings(45, 0)
        view.draw(field, 60)
        assert pygame.image.tobytes(view.surface.subsurface(FIELD_RECT), "RGB") != normal
        assert tuple(astuple(cell) for cell in field.cells) == before
        assert field.dynamic.phase_seconds == phase
        assert source.getstate() == random_state
        button = next(
            button for button in view.reflection_buttons if button.command is ReflectionAction.RESET
        )
        reset = (
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rectangle.center)
            if use_mouse
            else pygame.event.Event(pygame.KEYDOWN, key=pygame.K_o)
        )
        app.handle_event(reset, field, view, source)
        assert view.reflection == ReflectionSettings()
        view.draw(field, 60)
        assert pygame.image.tobytes(view.surface.subsurface(FIELD_RECT), "RGB") == normal
        field.hold()
        held = tuple(astuple(cell) for cell in field.cells)
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a), field, view, source)
        field.update(1)
        assert tuple(astuple(cell) for cell in field.cells) == held
    finally:
        pygame.quit()
