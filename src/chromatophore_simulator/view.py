"""Pygame rendering and control layout; drawing never changes simulation state."""

from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from math import pi
from types import MappingProxyType

import pygame

from chromatophore_simulator.dynamics import DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField, Pigment
from chromatophore_simulator.patterns import Pattern

WINDOW_SIZE = (1100, 820)
FIELD_RECT = (30, 82, 700, 550)
HEADER_ICON_SIZE = (64, 64)
HEADER_ICON_POSITION = (24, 10)
HEADER_TEXT_LEFT = 102
BACKGROUND = (24, 32, 37)
SKIN_COLOUR = (236, 220, 190)
# A clarity-first palette, rather than a physiological colour model. Keep it in
# the view so pigment identity and simulation behaviour do not depend on RGB values.
PIGMENT_COLOURS = MappingProxyType(
    {
        Pigment.YELLOW: (213, 158, 24),
        Pigment.RED: (190, 48, 43),
        Pigment.BROWN: (104, 49, 31),
        Pigment.BLACK: (30, 27, 26),
    }
)
TEXT_COLOUR = (239, 236, 226)
BUTTON_COLOUR = (53, 72, 80)
HOVER_COLOUR = (72, 99, 107)
MINIMUM_RADIUS = 0.8
RADIUS_SPACING_RATIO = 0.45
SKIN_SAMPLE_SPAN = 2  # Integrate roughly one 2 × 2 pigment tile per low-resolution sample.
SKIN_CONTRAST = 2.0  # Amplify pigment contrast against bare skin; 1.0 restores raw averaging.
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


class ViewMode(Enum):
    """Two presentations of the same live simulation state."""

    CHROMATOPHORES = "Chromatophores"
    SKIN = "Skin"


@dataclass(frozen=True)
class Button:
    """A clickable command and its screen-space rectangle."""

    command: Command | Pattern | ViewMode | DynamicDisplay | DynamicAction
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
        icon_resource = files("chromatophore_simulator").joinpath("assets/octopus.png")
        with icon_resource.open("rb") as icon_file:
            self.header_icon = pygame.transform.smoothscale(
                pygame.image.load(icon_file, "octopus.png"), HEADER_ICON_SIZE
            )
        self.mode = ViewMode.CHROMATOPHORES
        self.buttons = tuple(
            Button(
                command,
                pygame.Rect(30 + (index % 3) * 240, 651 + (index // 3) * 58, 220, 48),
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
    ) -> Command | Pattern | ViewMode | DynamicDisplay | DynamicAction | None:
        """Find the button under a mouse position.

        :param position: Window coordinates in pixels, measured from top left.
        :return: The matching command, or None outside the buttons.
        """
        for button in (
            *self.buttons,
            *self.pattern_buttons,
            *self.dynamic_buttons,
            *self.view_buttons,
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
        self.surface.blit(mode_label, (490, 52))
        rectangle = pygame.Rect(FIELD_RECT)
        pygame.draw.rect(self.surface, SKIN_COLOUR, rectangle)

        # Use the tighter dimension for both axes: cells stay equally spaced and the
        # entire grid fits, even when the field and the skin patch have different shapes.
        spacing = min(rectangle.width / field.columns, rectangle.height / field.rows)

        # Keep expanded neighbours separated. Contracted cells retain a small dot,
        # capped at the maximum radius so very dense grids cannot invert the size range.
        maximum_radius = spacing * RADIUS_SPACING_RATIO
        minimum_radius = min(MINIMUM_RADIUS, maximum_radius)

        # Centre a square-spaced grid within the available rectangular skin patch.
        left = rectangle.centerx - field.columns * spacing / 2
        top = rectangle.centery - field.rows * spacing / 2
        for index, cell in enumerate(field.cells):
            # Cells are stored row by row. The half-spacing offset places each disc
            # in the middle of its grid slot rather than on the slot's upper-left edge.
            row, column = divmod(index, field.columns)
            centre = (left + (column + 0.5) * spacing, top + (row + 0.5) * spacing)

            # Map expansion [0, 1] linearly onto the visible radius range. This makes
            # radius, not area, proportional to expansion: area grows with radius squared.
            # Read the current animated state; targets and timing belong to the model.
            radius = minimum_radius + cell.expansion * (maximum_radius - minimum_radius)

            # Antialiasing softens pixel edges as the radius changes by fractional pixels.
            # Each organ keeps its own pigment; the field's appearance comes from
            # the visible areas of these differently coloured discs together.
            pygame.draw.aacircle(self.surface, PIGMENT_COLOURS[cell.pigment], centre, radius)

        if self.mode is ViewMode.SKIN:
            # Integrate only the occupied grid, excluding the decorative skin margins.
            # Skin samples come directly from current cell coverage, never a previous frame.
            grid_rectangle = pygame.Rect(
                round(left),
                round(top),
                max(1, round(field.columns * spacing)),
                max(1, round(field.rows * spacing)),
            ).clip(rectangle)
            self._draw_skin(grid_rectangle, field, spacing)

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
        ):
            # Hover highlighting is visual feedback only; event handling applies commands.
            colour = (
                HOVER_COLOUR
                if button.rectangle.collidepoint(pygame.mouse.get_pos())
                else BUTTON_COLOUR
            )
            pygame.draw.rect(self.surface, colour, button.rectangle, border_radius=7)
            label_text = button.command.value
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
        hint = self.font.render(
            "Click settings to cycle  ·  Delay lags the moving signal"
            if field.dynamic
            else "Click settings to cycle  ·  Rates apply now; delay applies to new targets",
            True,
            TEXT_COLOUR,
        )
        self.surface.blit(hint, (30, 769))
        exit_hint = self.font.render(
            "Keys: E / C / R and 1 / 2 / 3   ·   Tab: switch view   ·   Esc: exit",
            True,
            TEXT_COLOUR,
        )
        self.surface.blit(exit_hint, (30, 794))
        self._draw_pigment_legend()

    def _draw_skin(self, rectangle: pygame.Rect, field: ChromatophoreField, spacing: float) -> None:
        """Integrate pigment coverage directly, avoiding pixel-grid sampling artefacts.

        :param rectangle: Occupied grid bounds in the display surface, in pixels.
        :param field: Current cell states, read without mutation.
        :param spacing: Distance between cell centres in the detailed view, in pixels.
        """
        sample_size = (
            max(1, (field.columns + SKIN_SAMPLE_SPAN - 1) // SKIN_SAMPLE_SPAN),
            max(1, (field.rows + SKIN_SAMPLE_SPAN - 1) // SKIN_SAMPLE_SPAN),
        )

        samples = pygame.Surface(sample_size)
        maximum_radius = spacing * RADIUS_SPACING_RATIO
        minimum_radius = min(MINIMUM_RADIUS, maximum_radius)

        for sample_y in range(sample_size[1]):
            for sample_x in range(sample_size[0]):
                totals = [0.0, 0.0, 0.0]
                count = 0

                # Integrate complete cell slots rather than shrinking a raster image.
                # Raster resampling can alternately capture discs and pale gaps, creating
                # a false grid. Exact circle area is independent of pixel alignment.
                for row in range(
                    sample_y * SKIN_SAMPLE_SPAN,
                    min((sample_y + 1) * SKIN_SAMPLE_SPAN, field.rows),
                ):
                    for column in range(
                        sample_x * SKIN_SAMPLE_SPAN,
                        min((sample_x + 1) * SKIN_SAMPLE_SPAN, field.columns),
                    ):
                        cell = field.cells[row * field.columns + column]
                        radius = minimum_radius + cell.expansion * (maximum_radius - minimum_radius)

                        # Each cell occupies a square slot of side length spacing but its pigment is
                        # a circle - calculate how much of the square is covered
                        coverage = pi * (radius / spacing) ** 2
                        pigment = PIGMENT_COLOURS[cell.pigment]

                        # For each red, green, and blue colour channel mix the pigment with the
                        # colout for uncovered skin
                        for channel in range(3):
                            totals[channel] += (
                                SKIN_COLOUR[channel] * (1 - coverage) + pigment[channel] * coverage
                            )
                        count += 1

                # Average only actual cells, including partial tiles at odd-sized edges.
                samples.set_at(
                    (sample_x, sample_y), tuple(round(total / count) for total in totals)
                )

        # Averaging includes the deliberately wide diagnostic gaps between discs,
        # which dilutes their colour. Amplify each sample's difference from bare skin
        # before enlargement: skin + gain * (sample - skin). Bare skin stays unchanged.
        # A fixed gain avoids brightness pumping as patterns animate; clamp channels
        # to valid RGB values. Work on the small sample grid to keep this inexpensive.
        for y in range(samples.get_height()):
            for x in range(samples.get_width()):
                colour = samples.get_at((x, y))
                enhanced = tuple(
                    max(0, min(255, round(base + SKIN_CONTRAST * (channel - base))))
                    for channel, base in zip(colour[:3], SKIN_COLOUR, strict=True)
                )
                samples.set_at((x, y), enhanced)

        # Smooth enlargement blends sample boundaries into a continuous surface. This
        # is a visual approximation of viewing distance, not a biological optical model.
        skin = pygame.transform.smoothscale(samples, rectangle.size)
        self.surface.blit(skin, rectangle)

    def _draw_pigment_legend(self) -> None:
        """Identify the four pigment colours and their alternating arrangement."""
        heading = self.title_font.render("Pigments", True, TEXT_COLOUR)
        self.surface.blit(heading, (760, 582))
        for index, pigment in enumerate(Pigment):
            # Match the field's 2 × 2 tile in the legend, with named colour swatches.
            left = 760 + (index % 2) * 155
            top = 625 + (index // 2) * 42
            swatch = pygame.Rect(left, top, 26, 26)
            pygame.draw.rect(self.surface, PIGMENT_COLOURS[pigment], swatch, border_radius=5)
            pygame.draw.rect(self.surface, TEXT_COLOUR, swatch, width=1, border_radius=5)
            label = self.font.render(pigment.value, True, TEXT_COLOUR)
            self.surface.blit(label, (left + 36, top + 4))
        note = self.font.render("View buttons below · Tab to switch", True, TEXT_COLOUR)
        self.surface.blit(note, (760, 714))
