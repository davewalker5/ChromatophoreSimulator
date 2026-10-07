"""Application lifecycle and input dispatch for the chromatophore simulator."""

from dataclasses import replace
from importlib.resources import files
from random import Random

import pygame

from chromatophore_simulator.dynamics import DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField
from chromatophore_simulator.patterns import Pattern
from chromatophore_simulator.view import (
    DYNAMIC_SHORTCUTS,
    PATTERN_SHORTCUTS,
    WINDOW_SIZE,
    Command,
    DynamicAction,
    FieldView,
    ViewMode,
)

TARGET_FRAMES_PER_SECOND = 60
MAXIMUM_FRAME_SECONDS = 0.1
RATE_PRESETS = (0.25, 0.5, 1.0, 2.0, 4.0)
DELAY_PRESETS = (0.0, 0.25, 0.5, 1.0, 2.0)


def _next_preset(current: float, presets: tuple[float, ...]) -> float:
    """Select the next greater preset, wrapping at the maximum.

    :param current: Current parameter value, which may lie between presets.
    :param presets: Non-empty, ascending sequence of supported UI values.
    :return: Next available value.
    """
    return next((value for value in presets if value > current), presets[0])


def apply_command(
    field: ChromatophoreField,
    command: Command | Pattern | DynamicDisplay | DynamicAction,
    random_source: Random,
) -> None:
    """Apply a global command to the existing population.

    :param field: Field whose targets will be updated.
    :param command: User-selected action.
    :param random_source: Generator used for random targets.
    """
    if isinstance(command, DynamicDisplay):
        field.start_dynamic(command, random_source)
        return
    if command is DynamicAction.HOLD:
        field.hold()
        return
    if command is DynamicAction.SPEED:
        if field.dynamic is not None:
            field.dynamic.speed = _next_preset(field.dynamic.speed, (0.5, 1.0, 2.0, 4.0))
        return
    if isinstance(command, Pattern):
        field.apply_pattern(command, random_source)
        return
    match command:
        case Command.EXPAND:
            field.set_expansion(1.0)
        case Command.CONTRACT:
            field.set_expansion(0.0)
        case Command.RANDOMISE:
            field.randomise(random_source)
        case Command.EXPANSION_RATE:
            field.response = replace(
                field.response,
                expansion_rate=_next_preset(field.response.expansion_rate, RATE_PRESETS),
            )
        case Command.CONTRACTION_RATE:
            field.response = replace(
                field.response,
                contraction_rate=_next_preset(field.response.contraction_rate, RATE_PRESETS),
            )
        case Command.RESPONSE_DELAY:
            field.response = replace(
                field.response,
                response_delay=_next_preset(field.response.response_delay, DELAY_PRESETS),
            )


def handle_event(
    event: pygame.event.Event,
    field: ChromatophoreField,
    view: FieldView,
    random_source: Random,
) -> bool:
    """Dispatch keyboard and left-click commands, or request shutdown.

    :param event: Pygame event to process.
    :param field: Simulation receiving commands.
    :param view: Control layout used for mouse hit testing.
    :param random_source: Generator used for random targets.
    :return: False for window close or Escape, otherwise True.
    """
    command = None
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            return False
        if event.key == pygame.K_TAB:
            view.toggle_mode()
            return True
        command = {
            pygame.K_e: Command.EXPAND,
            pygame.K_c: Command.CONTRACT,
            pygame.K_r: Command.RANDOMISE,
            pygame.K_1: Command.EXPANSION_RATE,
            pygame.K_2: Command.CONTRACTION_RATE,
            pygame.K_3: Command.RESPONSE_DELAY,
            pygame.K_SPACE: DynamicAction.HOLD,
            pygame.K_4: DynamicAction.SPEED,
        }.get(event.key)
        if command is None:
            command = {
                pygame.key.key_code(shortcut.lower()): pattern
                for pattern, shortcut in (*PATTERN_SHORTCUTS, *DYNAMIC_SHORTCUTS)
            }.get(event.key)
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        command = view.command_at(event.pos)
    if isinstance(command, ViewMode):
        # Presentation belongs to the view; switching never reissues model targets.
        view.mode = command
    elif command is not None:
        apply_command(field, command, random_source)
    return True


def main() -> None:
    """Run the graphical simulator until the user closes it; always release SDL."""
    try:
        # Initialise only the display and text systems; this simulation needs no audio.
        pygame.display.init()
        pygame.font.init()

        # Load the bundled icon through package resources so launching from another
        # working directory (or an installed package) still finds the same artwork.
        icon_resource = files("chromatophore_simulator").joinpath("assets/octopus.png")
        with icon_resource.open("rb") as icon_file:
            # Set before window creation; SDL also uses this for the macOS Dock.
            pygame.display.set_icon(pygame.image.load(icon_file, "octopus.png"))

        # The display surface is the drawing destination shared with the renderer.
        surface = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Chromatophore Simulator — Dynamic Displays")

        # Keep model state separate from drawing. Both objects persist across frames,
        # so commands change the existing population rather than rebuilding the field.
        view = FieldView(surface)
        field = ChromatophoreField()
        random_source = Random()

        # Randomise targets, not current sizes: the initially contracted cells animate
        # into the opening display using the same update logic as later user commands.
        field.randomise(random_source)
        clock = pygame.time.Clock()
        running = True
        while running:
            # tick limits the frame rate and reports elapsed milliseconds; divide by
            # 1000 because model rates and delays use seconds. Cap unusually long frames
            # so returning from suspension advances only a small amount of simulation
            # time, preserving visible transitions instead of jumping to their end.
            elapsed_seconds = min(
                clock.tick(TARGET_FRAMES_PER_SECOND) / 1000, MAXIMUM_FRAME_SECONDS
            )

            # Process queued input before updating, allowing new targets or response
            # settings to take effect in this frame. A close request stops event handling.
            for event in pygame.event.get():
                if not handle_event(event, field, view, random_source):
                    running = False
                    break
            if running:
                # Advance the model, draw its resulting state, then present the finished
                # frame. draw writes to the surface; flip makes that frame visible.
                # get_fps supplies a measured diagnostic, not the simulation time step.
                field.update(elapsed_seconds)
                view.draw(field, clock.get_fps())
                pygame.display.flip()
    finally:
        # Release Pygame resources on both normal exit and errors, including failures
        # during startup. Exceptions still propagate after cleanup for diagnosis.
        pygame.quit()
