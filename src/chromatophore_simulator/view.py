"""Coordinate desktop presentation, controls and field layout.

This view owns button geometry, hit testing, labels and mode selection. It passes
read-only field state and display coordinates to the dedicated chromatophore and
skin renderers. Application commands are still executed by app.py.
"""

from dataclasses import dataclass
from enum import Enum
from importlib.resources import files

import pygame

from chromatophore_simulator.chromatophore_renderer import PIGMENT_COLOURS, draw_chromatophores
from chromatophore_simulator.dynamics import DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField, Pigment
from chromatophore_simulator.patterns import Pattern
from chromatophore_simulator.reflection import ReflectionSettings
from chromatophore_simulator.skin_renderer import SKIN_COLOUR, draw_skin

WINDOW_SIZE = (1100, 820)
FIELD_RECT = (30, 82, 700, 550)
FIELD_CONTROL_TOP = 651
FIELD_CONTROL_BUTTON_SIZE = (220, 40)
FIELD_CONTROL_ROW_SPACING = 50
HEADER_ICON_SIZE = (64, 64)
HEADER_ICON_POSITION = (24, 10)
HEADER_TEXT_LEFT = 102
BACKGROUND = (24, 32, 37)
TEXT_COLOUR = (239, 236, 226)
BUTTON_COLOUR = (53, 72, 80)
HOVER_COLOUR = (72, 99, 107)
PATTERN_SHORTCUTS = (
    (Pattern.UNIFORM, "U"),
    (Pattern.CHECKERBOARD, "B"),
    (Pattern.HORIZONTAL_BANDS, "H"),
    (Pattern.VERTICAL_BANDS, "V"),
    (Pattern.SPOTS, "S"),
    (Pattern.RANDOM_MOTTLE, "M"),
    (Pattern.RADIAL_GRADIENT, "G"),
)


DYNAMIC_SHORTCUTS = (
    (DynamicDisplay.TRAVELLING_WAVE, "W"),
    (DynamicDisplay.RADIAL_PULSE, "P"),
    (DynamicDisplay.FLASH, "F"),
    (DynamicDisplay.MOVING_BANDS, "N"),
    (DynamicDisplay.LOCAL_EXCITATION, "L"),
    (DynamicDisplay.CHANGING_MOTTLE, "T"),
)


class DynamicAction(Enum):
    """Controls for running animated displays."""

    HOLD = "Hold [Space]"
    SPEED = "Speed [4]"


class Command(Enum):
    """Global target commands and response parameter controls."""

    EXPAND = "Expand all [E]"
    CONTRACT = "Contract all [C]"
    RANDOMISE = "Randomise [R]"
    EXPANSION_RATE = "Expansion [1]"
    CONTRACTION_RATE = "Contraction [2]"
    RESPONSE_DELAY = "Delay [3]"


class ReflectionAction(Enum):
    """Presentation-only controls for camera and illumination directions."""

    VIEW = "View angle [A]"
    LIGHT = "Light angle [I]"
    RESET = "Reset angles [O]"


class TimingAction(Enum):
    """Switch between smooth local kinetics and uniform linear motion."""

    TOGGLE = "Natural timing [9]"


class PigmentAction(Enum):
    """Shared controls for the pigment target multipliers."""

    RESET = "Reset pigment levels [0]"


class ViewMode(Enum):
    """Two presentations of the same live simulation state."""

    CHROMATOPHORES = "Chromatophores"
    SKIN = "Skin"


@dataclass(frozen=True)
class Button:
    """A clickable command and its screen-space rectangle."""

    command: (
        Command
        | Pattern
        | ViewMode
        | DynamicDisplay
        | DynamicAction
        | Pigment
        | PigmentAction
        | TimingAction
        | ReflectionAction
    )
    rectangle: pygame.Rect


class FieldView:
    """Draw the field and a small, discoverable control panel."""

    def __init__(self, surface: pygame.Surface) -> None:
        """Create fonts and controls for the fixed-size application window.

        :param surface: Destination surface with dimensions WINDOW_SIZE.
        """
        self.surface = surface
        self.font = pygame.font.Font(None, 24)
        self.title_font = pygame.font.Font(None, 34)
        # Load and scale once, then reuse the same artwork for every frame. Package
        # resources keep the header working when launched outside the project folder.
        icon_resource = files("chromatophore_simulator").joinpath("assets/cuttlefish.png")
        with icon_resource.open("rb") as icon_file:
            self.header_icon = pygame.transform.smoothscale(
                pygame.image.load(icon_file, "cuttlefish.png"), HEADER_ICON_SIZE
            )
        self.mode = ViewMode.CHROMATOPHORES
        self.reflection = ReflectionSettings()
        self.buttons = tuple(
            Button(
                command,
                pygame.Rect(
                    (
                        30 + (index % 3) * 240,
                        FIELD_CONTROL_TOP + (index // 3) * FIELD_CONTROL_ROW_SPACING,
                    ),
                    FIELD_CONTROL_BUTTON_SIZE,
                ),
            )
            for index, command in enumerate(Command)
        )
        self.pattern_buttons = tuple(
            Button(pattern, pygame.Rect(760 + (index % 2) * 160, 120 + (index // 2) * 42, 150, 36))
            for index, (pattern, _) in enumerate(PATTERN_SHORTCUTS)
        )
        self.dynamic_buttons = tuple(
            Button(display, pygame.Rect(760 + (index % 2) * 160, 352 + (index // 2) * 42, 150, 36))
            for index, (display, _) in enumerate(DYNAMIC_SHORTCUTS)
        ) + (
            Button(DynamicAction.HOLD, pygame.Rect(760, 485, 150, 36)),
            Button(DynamicAction.SPEED, pygame.Rect(920, 485, 150, 36)),
        )
        self.pigment_buttons = tuple(
            Button(pigment, pygame.Rect(760 + (index % 2) * 160, 620 + (index // 2) * 42, 150, 36))
            for index, pigment in enumerate(Pigment)
        ) + (Button(PigmentAction.RESET, pygame.Rect(760, 708, 310, 32)),)
        self.reflection_buttons = tuple(
            Button(
                action,
                pygame.Rect(
                    (30 + index * 240, FIELD_CONTROL_TOP + 2 * FIELD_CONTROL_ROW_SPACING),
                    FIELD_CONTROL_BUTTON_SIZE,
                ),
            )
            for index, action in enumerate(ReflectionAction)
        )
        self.timing_buttons = (Button(TimingAction.TOGGLE, pygame.Rect(490, 44, 240, 30)),)
        self.view_buttons = tuple(
            Button(mode, pygame.Rect(760 + index * 160, 756, 150, 42))
            for index, mode in enumerate(ViewMode)
        )

    def toggle_mode(self) -> None:
        """Switch presentation immediately without touching simulation state."""
        self.mode = (
            ViewMode.SKIN if self.mode is ViewMode.CHROMATOPHORES else ViewMode.CHROMATOPHORES
        )

    def command_at(
        self, position: tuple[int, int]
    ) -> (
        Command
        | Pattern
        | ViewMode
        | DynamicDisplay
        | DynamicAction
        | Pigment
        | PigmentAction
        | TimingAction
        | ReflectionAction
        | None
    ):
        """Find the button under a mouse position.

        :param position: Window coordinates in pixels, measured from top left.
        :return: The matching command, or None outside the buttons.
        """
        for button in (
            *self.buttons,
            *self.pattern_buttons,
            *self.dynamic_buttons,
            *self.view_buttons,
            *self.timing_buttons,
            *self.reflection_buttons,
            *self.pigment_buttons,
        ):
            if button.rectangle.collidepoint(position):
                return button.command
        return None

    def draw(self, field: ChromatophoreField, frames_per_second: float) -> None:
        """Render the live field as individual discs or a visually integrated skin.

        :param field: Read-only simulation state to display.
        :param frames_per_second: Measured frame rate for the diagnostic label.
        """
        # Redraw the whole frame so contracting discs and changing labels leave no trails.
        # All positions below are pixels, measured from the window's top-left corner.
        self.surface.fill(BACKGROUND)
        self.surface.blit(self.header_icon, HEADER_ICON_POSITION)
        title = self.title_font.render("Chromatophore Simulator", True, TEXT_COLOUR)
        self.surface.blit(title, (HEADER_TEXT_LEFT, 18))
        subtitle = self.font.render(
            f"{field.columns} × {field.rows}  /  {len(field.cells):,} cells"
            f"     ·     {frames_per_second:.0f} FPS",
            True,
            TEXT_COLOUR,
        )
        self.surface.blit(subtitle, (HEADER_TEXT_LEFT, 52))
        mode_label = self.font.render(f"View: {self.mode.value}", True, TEXT_COLOUR)
        self.surface.blit(mode_label, (490, 18))
        rectangle = pygame.Rect(FIELD_RECT)
        pygame.draw.rect(self.surface, SKIN_COLOUR, rectangle)

        # Use the tighter dimension for both axes: cells stay equally spaced and the
        # entire grid fits, even when the field and the skin patch have different shapes.
        spacing = min(rectangle.width / field.columns, rectangle.height / field.rows)

        # Centre a square-spaced grid within the available rectangular skin patch.
        left = rectangle.centerx - field.columns * spacing / 2
        top = rectangle.centery - field.rows * spacing / 2
        draw_chromatophores(self.surface, field, left, top, spacing)

        if self.mode is ViewMode.SKIN:
            # Integrate only the occupied grid, excluding the decorative skin margins.
            # Skin samples come directly from current cell coverage, never a previous frame.
            grid_rectangle = pygame.Rect(
                round(left),
                round(top),
                max(1, round(field.columns * spacing)),
                max(1, round(field.rows * spacing)),
            ).clip(rectangle)
            draw_skin(self.surface, grid_rectangle, field, spacing, self.reflection)

        heading = self.title_font.render("Patterns", True, TEXT_COLOUR)
        self.surface.blit(heading, (760, 18))
        selection = self.font.render(f"Target: {field.target_description}", True, TEXT_COLOUR)
        self.surface.blit(selection, (760, 56))
        pattern_hint = self.font.render("Select to animate towards a pattern", True, TEXT_COLOUR)
        self.surface.blit(pattern_hint, (760, 85))

        dynamic_heading = self.title_font.render("Dynamic displays", True, TEXT_COLOUR)
        self.surface.blit(dynamic_heading, (760, 310))
        for button in (
            *self.buttons,
            *self.pattern_buttons,
            *self.dynamic_buttons,
            *self.view_buttons,
            *self.timing_buttons,
            *self.reflection_buttons,
            *self.pigment_buttons,
        ):
            # Hover highlighting is visual feedback only; event handling applies commands.
            colour = (
                HOVER_COLOUR
                if button.rectangle.collidepoint(pygame.mouse.get_pos())
                else BUTTON_COLOUR
            )
            pygame.draw.rect(self.surface, colour, button.rectangle, border_radius=7)
            label_text = button.command.value
            if button.command is ReflectionAction.VIEW:
                label_text += f": {self.reflection.view_angle:g}°"
            elif button.command is ReflectionAction.LIGHT:
                label_text += f": {self.reflection.light_angle:g}°"
            if button.command is TimingAction.TOGGLE:
                label_text += ": on" if field.natural_timing else ": off"
                if field.natural_timing:
                    pygame.draw.rect(
                        self.surface, TEXT_COLOUR, button.rectangle, width=1, border_radius=7
                    )
            if isinstance(button.command, Pigment):
                index = tuple(Pigment).index(button.command)
                label_text += f" [{index + 5}]: {field.pigment_levels[button.command]:.0%}"
                pygame.draw.rect(
                    self.surface,
                    PIGMENT_COLOURS[button.command],
                    button.rectangle.inflate(-4, -4).clip(
                        pygame.Rect(button.rectangle.left + 2, button.rectangle.top + 2, 5, 32)
                    ),
                )
            if button.command is self.mode:
                pygame.draw.rect(
                    self.surface, TEXT_COLOUR, button.rectangle, width=2, border_radius=7
                )
            if isinstance(button.command, (Pattern, DynamicDisplay)):
                shortcut = dict((*PATTERN_SHORTCUTS, *DYNAMIC_SHORTCUTS))[button.command]
                label_text += f" [{shortcut}]"
                # Highlight the selected target even while cells are still transitioning.
                if field.target_description == button.command.value:
                    pygame.draw.rect(
                        self.surface, TEXT_COLOUR, button.rectangle, width=2, border_radius=7
                    )

            # Read settings each frame so button labels reflect the active model values.
            # Rates are expansion units per second; response delay is measured in seconds.
            match button.command:
                case Command.EXPANSION_RATE:
                    label_text += f": {field.response.expansion_rate:g}/s"
                case Command.CONTRACTION_RATE:
                    label_text += f": {field.response.contraction_rate:g}/s"
                case Command.RESPONSE_DELAY:
                    label_text += f": {field.response.response_delay:g} s"
            if button.command is DynamicAction.SPEED:
                label_text += f": {field.dynamic.speed:g}×" if field.dynamic else ": —"
            label = self.font.render(label_text, True, TEXT_COLOUR)
            if label.get_width() > button.rectangle.width - 10:
                # Keep longer pattern names legible in the compact two-column panel.
                label = pygame.font.Font(None, 19).render(label_text, True, TEXT_COLOUR)

            # Centre using the rendered text's bounds so different label lengths fit neatly.
            self.surface.blit(label, label.get_rect(center=button.rectangle.center))
        exit_hint = self.font.render(
            "A / I: angles  ·  O: reset angles  ·  Tab: switch view  ·  Esc: exit",
            True,
            TEXT_COLOUR,
        )
        self.surface.blit(exit_hint, (30, FIELD_CONTROL_TOP + 3 * FIELD_CONTROL_ROW_SPACING))
        self._draw_pigment_legend()

    def _draw_pigment_legend(self) -> None:
        """Label the pigment controls; buttons retain their own colour indicators."""
        heading = self.title_font.render("Pigment levels", True, TEXT_COLOUR)
        self.surface.blit(heading, (760, 550))
        note = self.font.render("Click to cycle target strength", True, TEXT_COLOUR)
        self.surface.blit(note, (760, 585))
