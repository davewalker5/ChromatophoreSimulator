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


def test_reference_response_is_restrained_and_covers_the_skin() -> None:
    """The distributed reference is uniform, bounded and weaker than old patch peaks."""

    responses = reflection_responses()
    assert all(response.colour == IRIDOPHORE_COLOUR for response in responses)
    assert all(response.strength == pytest.approx(1) for response in responses)
    for x, y in ((0, 0), (0.24, 0.3), (0.76, 0.36), (0.48, 0.78), (0.5, 0.5), (1, 1)):
        expected = tuple(
            round(base + IRIDOPHORE_STRENGTH * (colour - base))
            for base, colour in zip(SKIN_COLOUR, IRIDOPHORE_COLOUR, strict=True)
        )
        assert iridophore_base(x, y, responses) == expected


def test_angular_responses_are_bounded_fixed_and_smooth() -> None:
    """Supported angles stay finite; tiny changes do not cause abrupt colour jumps."""
    for view in ANGLE_PRESETS:
        for light in ANGLE_PRESETS:
            settings = ReflectionSettings(view, light)
            responses = reflection_responses(settings)
            assert responses == reflection_responses(settings)
            assert all(0 <= response.strength <= 2.9 for response in responses)
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


def test_directional_contrast_is_visible_for_both_angle_controls() -> None:
    """Off-axis patches fade visibly without raising the straight-on strength."""
    assert reflection_responses(ReflectionSettings(60, 0))[24].strength < 0.35
    assert reflection_responses(ReflectionSettings(0, 60))[24].strength < 0.18
    aligned = reflection_responses(ReflectionSettings(30, 0))
    assert aligned[27].strength > 2.5 * aligned[21].strength


def test_angled_highlights_survive_backing_blending() -> None:
    """A normal UI angle step creates a visible patch, not just a tiny multiplier change."""
    front = iridophore_base(0.05, 0.5)
    for settings in (ReflectionSettings(-45, 0), ReflectionSettings(0, -45)):
        responses = reflection_responses(settings)
        assert responses[21].strength > 1.8
        angled = iridophore_base(0.05, 0.5, responses)
        assert max(abs(a - b) for a, b in zip(front, angled, strict=True)) > 12


def test_tilting_blue_shifts_and_selects_different_patch_orientations() -> None:
    """Oblique reflection shifts towards blue and follows preferred patch normals."""
    front = reflection_responses()
    tilted = reflection_responses(ReflectionSettings(60, 0))
    assert tilted[1].colour[2] / tilted[1].colour[1] > front[1].colour[2] / front[1].colour[1]
    assert tilted[24].strength < front[24].strength
    right = reflection_responses(ReflectionSettings(30, 0))
    left = reflection_responses(ReflectionSettings(-30, 0))
    assert right[27].strength > right[21].strength
    assert left[21].strength > left[27].strength
    assert reflection_responses(ReflectionSettings(0, 30)) != front
    invisible = reflection_responses(ReflectionSettings(60, -60))
    assert all(response.strength == 0 for response in invisible)
    assert iridophore_base(0.24, 0.3, invisible) == SKIN_COLOUR


def test_sheen_is_distributed_and_spatially_smooth() -> None:
    """Angle changes affect much of the field, including edges, without winner seams."""
    before = reflection_responses(ReflectionSettings(-45, 0))
    after = reflection_responses(ReflectionSettings(45, 0))
    changed = 0
    for row in range(11):
        for column in range(11):
            x, y = column / 10, row / 10
            first = iridophore_base(x, y, before)
            second = iridophore_base(x, y, after)
            changed += max(abs(a - b) for a, b in zip(first, second, strict=True)) >= 10
            nearby = iridophore_base(min(1, x + 0.001), y, after)
            assert max(abs(a - b) for a, b in zip(second, nearby, strict=True)) <= 1
    assert changed >= 80  # At least two thirds of the field, rather than one spot.


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
