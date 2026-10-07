"""Headless integration checks of actual drawing, input and shutdown."""

from collections.abc import Iterator
from dataclasses import astuple
from random import Random
from statistics import pvariance

import pygame
import pytest

from chromatophore_simulator import app
from chromatophore_simulator.model import ChromatophoreField, Pigment, ResponseParameters
from chromatophore_simulator.patterns import Pattern, generate_targets
from chromatophore_simulator.view import (
    FIELD_RECT,
    PATTERN_SHORTCUTS,
    PIGMENT_COLOURS,
    WINDOW_SIZE,
    FieldView,
    ViewMode,
)


@pytest.fixture
def view(monkeypatch: pytest.MonkeyPatch) -> Iterator[FieldView]:
    """Initialise a real SDL surface without opening a desktop window.

    :param monkeypatch: Fixture setting a temporary SDL video driver.
    :return: Renderer backed by a headless display.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    pygame.font.init()
    try:
        yield FieldView(pygame.display.set_mode(WINDOW_SIZE))
    finally:
        pygame.quit()


def test_rendering_changes_pixels_without_changing_model(view: FieldView) -> None:
    """Expansion visibly changes the full default field without renderer mutation.

    :param view: Headless renderer.
    """
    field = ChromatophoreField(response=ResponseParameters(1.0, 1.0))
    view.draw(field, 60.0)
    contracted = pygame.image.tobytes(view.surface, "RGB")
    field.set_expansion(1.0)
    field.update(1.0)
    view.draw(field, 60.0)
    expanded = pygame.image.tobytes(view.surface, "RGB")
    assert contracted != expanded
    assert all(cell.expansion == 1.0 for cell in field.cells)


@pytest.mark.parametrize("use_mouse", [False, True])
def test_controls(view: FieldView, use_mouse: bool) -> None:
    """Both keyboard and mouse dispatch all three commands to existing cells.

    :param view: Headless renderer and button layout.
    :param use_mouse: Whether to exercise mouse instead of keyboard controls.
    """
    field = ChromatophoreField(2, 2)
    original_cells = field.cells
    for index, key in enumerate((pygame.K_e, pygame.K_c, pygame.K_r)):
        if use_mouse:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=view.buttons[index].rectangle.center
            )
        else:
            event = pygame.event.Event(pygame.KEYDOWN, key=key)
        assert app.handle_event(event, field, view, Random(42))
        targets = [cell.target_expansion for cell in field.cells]
        if index < 2:
            assert targets == [1.0 if index == 0 else 0.0] * 4
        else:
            assert len(set(targets)) == 4
    assert field.cells is original_cells


def test_unhandled_input_and_exit(view: FieldView) -> None:
    """Outside clicks and unknown keys do nothing; Escape and window close exit.

    :param view: Headless renderer.
    """
    field = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0))
    for event in (
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=view.buttons[0].rectangle.center),
    ):
        assert app.handle_event(event, field, view, Random(0))
    assert field.cells[0].target_expansion == 0.0
    for event in (
        pygame.event.Event(pygame.QUIT),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
    ):
        assert not app.handle_event(event, field, view, Random(0))


def test_main_renders_then_shuts_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the application loop for one real frame and verify display cleanup.

    :param monkeypatch: Fixture supplying deterministic event batches.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    batches = iter([[], [pygame.event.Event(pygame.QUIT)]])
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))
    app.main()
    assert not pygame.display.get_init()
    assert not pygame.font.get_init()


@pytest.mark.parametrize("use_mouse", [False, True])
def test_response_controls(view: FieldView, use_mouse: bool) -> None:
    """Response controls cycle independently without changing targets or cells.

    :param view: Headless renderer and control layout.
    :param use_mouse: Whether to exercise mouse or keyboard controls.
    """
    field = ChromatophoreField(1, 1, ResponseParameters(1.0, 1.0))
    field.set_expansion(1.0)
    field.update(0.25)
    original_cell = field.cells[0]
    for index, key in enumerate((pygame.K_1, pygame.K_2, pygame.K_3), start=3):
        if use_mouse:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=view.buttons[index].rectangle.center
            )
        else:
            event = pygame.event.Event(pygame.KEYDOWN, key=key)
        assert app.handle_event(event, field, view, Random(42))
    assert field.response.expansion_rate == 2.0
    assert field.response.contraction_rate == 2.0
    assert field.response.response_delay == 0.25
    assert field.cells[0] is original_cell
    assert original_cell.expansion == 0.25
    assert original_cell.target_expansion == 1.0
    # A complete cycle returns each setting to the same value.
    for _ in range(5):
        for button in view.buttons[3:]:
            app.apply_command(field, button.command, Random(42))
    assert field.response.expansion_rate == 2.0
    assert field.response.contraction_rate == 2.0
    assert field.response.response_delay == 0.25
    view.draw(field, 60.0)


@pytest.mark.parametrize("use_mouse", [False, True])
def test_pattern_controls(view: FieldView, use_mouse: bool) -> None:
    """All pattern controls generate targets without snapping current cell sizes.

    :param view: Headless renderer and pattern panel.
    :param use_mouse: Whether to select by mouse or keyboard.
    """
    field = ChromatophoreField(response=ResponseParameters(1.0, 1.0))
    for index, (pattern, shortcut) in enumerate(PATTERN_SHORTCUTS):
        if use_mouse:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=view.pattern_buttons[index].rectangle.center,
            )
        else:
            event = pygame.event.Event(pygame.KEYDOWN, key=pygame.key.key_code(shortcut.lower()))
        assert app.handle_event(event, field, view, Random(42))
        assert field.target_description == pattern.value
        assert tuple(cell.target_expansion for cell in field.cells) == generate_targets(
            pattern, 50, 50, Random(42)
        )
        assert all(cell.expansion == 0.0 for cell in field.cells)
        view.draw(field, 60.0)


def test_renderer_uses_each_cells_pigment(view: FieldView) -> None:
    """The centres of the four discs show their own pigment colours, with no mutation.

    :param view: Headless renderer using the real palette and drawing implementation.
    """
    field = ChromatophoreField(2, 2, ResponseParameters(1.0, 1.0))
    field.set_expansion(1.0)
    field.update(1.0)
    original_state = tuple(
        (cell.pigment, cell.expansion, cell.target_expansion) for cell in field.cells
    )
    view.draw(field, 60.0)
    rectangle = pygame.Rect(FIELD_RECT)
    spacing = min(rectangle.width / 2, rectangle.height / 2)
    left = rectangle.centerx - spacing
    top = rectangle.centery - spacing
    for index, pigment in enumerate(Pigment):
        row, column = divmod(index, 2)
        centre = (int(left + (column + 0.5) * spacing), int(top + (row + 0.5) * spacing))
        assert view.surface.get_at(centre)[:3] == PIGMENT_COLOURS[pigment]
    assert (
        tuple((cell.pigment, cell.expansion, cell.target_expansion) for cell in field.cells)
        == original_state
    )


@pytest.mark.parametrize("use_mouse", [False, True])
def test_switching_views_preserves_animation_and_randomness(
    view: FieldView, use_mouse: bool
) -> None:
    """View changes leave cells, targets, delay countdowns and randomness untouched.

    :param view: Headless renderer.
    :param use_mouse: Whether to use direct view buttons rather than Tab.
    """
    field = ChromatophoreField(2, 2, ResponseParameters(1.0, 0.5, 0.5))
    reference = ChromatophoreField(2, 2, field.response)
    for candidate in (field, reference):
        candidate.set_expansion(1.0)
        candidate.update(0.25)
    cells = field.cells
    random_source = Random(42)
    random_state = random_source.getstate()
    before = tuple(astuple(cell) for cell in cells)
    assert view.mode is ViewMode.CHROMATOPHORES
    for mode in (ViewMode.SKIN, ViewMode.CHROMATOPHORES, ViewMode.SKIN):
        if use_mouse:
            button = next(button for button in view.view_buttons if button.command is mode)
            event = pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=button.rectangle.center
            )
        else:
            event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB)
        assert app.handle_event(event, field, view, random_source)
        view.draw(field, 60.0)
        assert view.mode is mode
        assert tuple(astuple(cell) for cell in cells) == before
    assert field.cells is cells
    assert field.response is reference.response
    assert field.target_description == reference.target_description
    assert random_source.getstate() == random_state
    for candidate in (field, reference):
        candidate.update(0.5)
    assert tuple(astuple(cell) for cell in cells) == tuple(
        astuple(cell) for cell in reference.cells
    )
    assert all(cell.expansion == pytest.approx(0.25) for cell in cells)


def test_skin_blends_pigments_and_is_reversible(view: FieldView) -> None:
    """Skin suppresses alternating pigment detail; returning restores the original discs.

    :param view: Headless renderer.
    """
    field = ChromatophoreField()
    field.set_expansion(1.0)
    field.update(4.0)
    view.draw(field, 60.0)
    rectangle = pygame.Rect(FIELD_RECT)
    original = pygame.image.tobytes(view.surface.subsurface(rectangle), "RGB")
    # Sample a line within the occupied grid, including pigment centres and gaps.
    detailed_values = [view.surface.get_at((x, 300)).r for x in range(200, 500)]
    view.mode = ViewMode.SKIN
    view.draw(field, 60.0)
    integrated = pygame.image.tobytes(view.surface.subsurface(rectangle), "RGB")
    skin_values = [view.surface.get_at((x, 300)).r for x in range(200, 500)]
    assert integrated != original
    assert pvariance(skin_values) < pvariance(detailed_values) / 10
    # Repeated drawing must start from the original discs, rather than blur again.
    view.draw(field, 60.0)
    assert pygame.image.tobytes(view.surface.subsurface(rectangle), "RGB") == integrated
    view.mode = ViewMode.CHROMATOPHORES
    view.draw(field, 60.0)
    assert pygame.image.tobytes(view.surface.subsurface(rectangle), "RGB") == original


@pytest.mark.parametrize("shape", [(1, 1), (1, 13), (13, 1), (3, 7), (50, 50)])
def test_skin_draws_current_expansion_and_keeps_controls_live(
    view: FieldView, shape: tuple[int, int]
) -> None:
    """Skin supports small/odd fields and changes only as current expansion advances.

    :param view: Headless renderer.
    :param shape: Rows and columns for the field.
    """
    field = ChromatophoreField(*shape, ResponseParameters(1.0, 1.0))
    view.mode = ViewMode.SKIN
    rectangle = pygame.Rect(FIELD_RECT)
    view.draw(field, 60.0)
    contracted = pygame.image.tobytes(view.surface.subsurface(rectangle), "RGB")
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e), field, view, Random(0))
    view.draw(field, 60.0)
    assert pygame.image.tobytes(view.surface.subsurface(rectangle), "RGB") == contracted
    field.update(1.0)
    view.draw(field, 60.0)
    assert pygame.image.tobytes(view.surface.subsurface(rectangle), "RGB") != contracted
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m), field, view, Random(42))
    assert field.target_description == "Random mottle"
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1), field, view, Random(42))
    assert field.response.expansion_rate == 2.0
    assert view.mode is ViewMode.SKIN


def test_skin_contrast_strengthens_patches_without_changing_model(
    view: FieldView, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contrast enhances pigment differences while preserving bare skin and cell state.

    :param view: Headless renderer.
    :param monkeypatch: Fixture temporarily selecting raw averaging for comparison.
    """
    from chromatophore_simulator import view as view_module

    field = ChromatophoreField()
    field.apply_pattern(Pattern.CHECKERBOARD, Random(0))
    field.update(4.0)
    before = tuple(astuple(cell) for cell in field.cells)
    view.mode = ViewMode.SKIN
    view.draw(field, 60.0)
    enhanced = view.surface.copy()
    monkeypatch.setattr(view_module, "SKIN_CONTRAST", 1.0)
    view.draw(field, 60.0)
    # Compare within the occupied field, avoiding margins and UI labels.
    enhanced_values = [enhanced.get_at((x, 115)).r for x in range(130, 620)]
    raw_values = [view.surface.get_at((x, 115)).r for x in range(130, 620)]
    assert pvariance(enhanced_values) > pvariance(raw_values) * 2
    assert enhanced.get_at((40, 100)) == view.surface.get_at((40, 100))
    assert tuple(astuple(cell) for cell in field.cells) == before


@pytest.mark.parametrize("expansion", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_uniform_skin_has_no_sampling_grid(view: FieldView, expansion: float) -> None:
    """Equal pigment tiles must produce a flat skin colour without raster aliasing.

    :param view: Headless renderer.
    :param expansion: Uniform expansion, including partially expanded discs.
    """
    field = ChromatophoreField()
    field.set_expansion(expansion)
    field.update(4.0)
    view.mode = ViewMode.SKIN
    view.draw(field, 60.0)
    # Probe both axes throughout the occupied square, excluding decorative margins.
    colours = {
        tuple(view.surface.get_at((x, y))[:3])
        for y in range(90, 625, 7)
        for x in range(112, 650, 7)
    }
    for channel in range(3):
        assert (
            max(colour[channel] for colour in colours) - min(colour[channel] for colour in colours)
            <= 1
        )


@pytest.mark.parametrize("use_mouse", [False, True])
def test_dynamic_controls(view: FieldView, use_mouse: bool) -> None:
    """Dynamic selection, speed, hold and view switching work together.

    :param view: Headless renderer.
    :param use_mouse: Select displays with mouse instead of keyboard.
    """
    from chromatophore_simulator.view import DYNAMIC_SHORTCUTS

    field = ChromatophoreField(5, 5)
    for index, (display, shortcut) in enumerate(DYNAMIC_SHORTCUTS):
        event = (
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=view.dynamic_buttons[index].rectangle.center
            )
            if use_mouse
            else pygame.event.Event(pygame.KEYDOWN, key=pygame.key.key_code(shortcut.lower()))
        )
        assert app.handle_event(event, field, view, Random(0))
        assert field.dynamic.display is display
        controller = field.dynamic
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4), field, view, Random(0))
        assert controller.speed == 2
        app.handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB), field, view, Random(0)
        )
        assert field.dynamic is controller
        field.update(0.1)
        view.draw(field, 60)
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE), field, view, Random(0))
    assert field.dynamic is None
