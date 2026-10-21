"""Pygame rendering and control layout; drawing never changes simulation state."""

from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from math import exp
from types import MappingProxyType

import pygame

from chromatophore_simulator.coverage import circle_rectangle_area
from chromatophore_simulator.dynamics import DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField, Pigment
from chromatophore_simulator.patterns import Pattern

WINDOW_SIZE = (1100, 820)
FIELD_RECT = (30, 82, 700, 550)
HEADER_ICON_SIZE = (64, 64)
HEADER_ICON_POSITION = (24, 10)
HEADER_TEXT_LEFT = 102
BACKGROUND = (24, 32, 37)
SKIN_COLOUR = (235, 232, 220)
IRIDOPHORE_COLOUR = (126, 179, 205)
IRIDOPHORE_STRENGTH = 0.28  # Fixed-light structural reflection, beneath pigment.

# Sepia officinalis-inspired palette under neutral daylight (D65 target).
# Illustrative sRGB values, not measured reflectance. Black represents dark brown.
IRIDOPHORE_PATCHES = (
    (0.24, 0.3, 0.15, 0.24),
    (0.76, 0.36, 0.13, 0.22),
    (0.48, 0.78, 0.22, 0.12),
)


def iridophore_base(x: float, y: float) -> tuple[int, ...]:
    """Approximate local reflection at normalised coordinates under fixed daylight.

    Patches are illustrative, not an anatomical map or an angle-dependent model.
    """
    patch = max(
        exp(-2 * (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2))
        for cx, cy, rx, ry in IRIDOPHORE_PATCHES
    )
    return tuple(
        round(backing + IRIDOPHORE_STRENGTH * patch * (reflection - backing))
        for backing, reflection in zip(SKIN_COLOUR, IRIDOPHORE_COLOUR, strict=True)
    )


PIGMENT_COLOURS = MappingProxyType(
    {
        Pigment.YELLOW: (190, 145, 52),
        Pigment.RED: (155, 74, 46),
        Pigment.BROWN: (85, 56, 40),
        Pigment.BLACK: (43, 34, 29),
    }
)

# Effective round-trip transmission per linear RGB channel, in [0, 1]. These
# illustrative coefficients include travel into and back out of the pigment.
# The untransmitted fraction uses the pigment's existing reflected colour.
PIGMENT_TRANSMISSION = MappingProxyType(
    {
        Pigment.YELLOW: (0.55, 0.35, 0.04),
        Pigment.RED: (0.35, 0.05, 0.02),
        Pigment.BROWN: (0.07, 0.04, 0.02),
        Pigment.BLACK: (0.015, 0.01, 0.008),
    }
)
SRGB_CHANNEL_MAXIMUM = 255
SRGB_LINEAR_THRESHOLD = 0.04045
LINEAR_SRGB_THRESHOLD = 0.0031308
SRGB_LINEAR_SCALE = 12.92
SRGB_OFFSET = 0.055
SRGB_SCALE = 1.055
SRGB_EXPONENT = 2.4


def _srgb_to_linear(channel: int) -> float:
    """Decode one sRGB channel to relative light intensity.

    :param channel: Display channel in the inclusive range 0 to 255.
    :return: Linear intensity in the inclusive range 0 to 1.
    """
    value = channel / SRGB_CHANNEL_MAXIMUM
    if value <= SRGB_LINEAR_THRESHOLD:
        return value / SRGB_LINEAR_SCALE
    return ((value + SRGB_OFFSET) / SRGB_SCALE) ** SRGB_EXPONENT


def _linear_to_srgb(value: float) -> int:
    """Encode linear light intensity as a clamped display channel.

    :param value: Relative linear light intensity, normally between 0 and 1.
    :return: Integer sRGB channel in the inclusive range 0 to 255.
    """
    value = max(0.0, min(1.0, value))
    if value <= LINEAR_SRGB_THRESHOLD:
        encoded = value * SRGB_LINEAR_SCALE
    else:
        encoded = SRGB_SCALE * value ** (1 / SRGB_EXPONENT) - SRGB_OFFSET
    return round(encoded * SRGB_CHANNEL_MAXIMUM)


def _pigment_reflections(backing: tuple[float, ...]) -> dict[Pigment, tuple[float, ...]]:
    """Filter backing light through each pigment without changing model state.

    The convex mixture bounds outgoing energy by the supplied backing and pigment
    reflection. It approximates RGB filtering, not a spectral scattering model.

    :param backing: Three linear RGB intensities, each between 0 and 1.
    :return: Linear RGB reflection for the pigment-covered part of each cell.
    """
    return {
        pigment: tuple(
            _srgb_to_linear(colour) * (1 - transmission) + light * transmission
            for colour, light, transmission in zip(
                PIGMENT_COLOURS[pigment], backing, PIGMENT_TRANSMISSION[pigment], strict=True
            )
        )
        for pigment in Pigment
    }


TEXT_COLOUR = (239, 236, 226)
BUTTON_COLOUR = (53, 72, 80)
HOVER_COLOUR = (72, 99, 107)
MINIMUM_RADIUS = 0.8
SKIN_SAMPLE_SPAN = 4  # Integrate four logical spacings per sample, including partial edges.
SKIN_CONTRAST = 2.0  # Display coverage boost, applied after fixed layout calibration.
SKIN_REFERENCE_RADIUS_RATIO = 0.45  # Preserve the pre-morphology layout's pigment density.
SKIN_SHARPNESS = 2.0  # Unsharp mask strength on the integrated pigment image.

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


def _skin_coverage_gain(field: ChromatophoreField) -> float:
    """Calibrate fixed morphology against the former regular layout's maximum area.

    Smaller organs need greater coverage compensation in the integrated view.
    Using maximum rather than current radii avoids brightness pumping as organs
    move. A single global factor preserves local size and pigment differences.
    The circle-area factor pi cancels from the ratio of the two area totals.

    :param field: Non-empty field with factory-generated positive maximum radii.
    :return: Dimensionless multiplier for integrated pigment coverage.
    """
    maximum_area = sum(organ.radius_ratio**2 for organ in field.geometry)
    return len(field.geometry) * SKIN_REFERENCE_RADIUS_RATIO**2 / maximum_area


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

    command: Command | Pattern | ViewMode | DynamicDisplay | DynamicAction | Pigment | PigmentAction
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
        self.pigment_buttons = tuple(
            Button(pigment, pygame.Rect(760 + (index % 2) * 160, 620 + (index // 2) * 42, 150, 36))
            for index, pigment in enumerate(Pigment)
        ) + (Button(PigmentAction.RESET, pygame.Rect(760, 708, 310, 32)),)
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
        self.surface.blit(mode_label, (490, 52))
        rectangle = pygame.Rect(FIELD_RECT)
        pygame.draw.rect(self.surface, SKIN_COLOUR, rectangle)

        # Use the tighter dimension for both axes: cells stay equally spaced and the
        # entire grid fits, even when the field and the skin patch have different shapes.
        spacing = min(rectangle.width / field.columns, rectangle.height / field.rows)

        # Fixed morphology bounds each organ's radius to avoid neighbour overlap.
        # Contracted organs retain a small diagnostic dot, capped by that radius.

        # Centre a square-spaced grid within the available rectangular skin patch.
        left = rectangle.centerx - field.columns * spacing / 2
        top = rectangle.centery - field.rows * spacing / 2
        for cell, organ in zip(field.cells, field.geometry, strict=True):
            centre = (left + organ.x * spacing, top + organ.y * spacing)
            maximum_radius = organ.radius_ratio * spacing
            minimum_radius = min(MINIMUM_RADIUS, maximum_radius)

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
        :param spacing: Pixels per logical target spacing in the detailed view.
        """
        sample_size = (
            max(1, (field.columns + SKIN_SAMPLE_SPAN - 1) // SKIN_SAMPLE_SPAN),
            max(1, (field.rows + SKIN_SAMPLE_SPAN - 1) // SKIN_SAMPLE_SPAN),
        )

        samples = pygame.Surface(sample_size)
        coverage_gain = _skin_coverage_gain(field)

        for sample_y in range(sample_size[1]):
            for sample_x in range(sample_size[0]):
                left = sample_x * SKIN_SAMPLE_SPAN
                top = sample_y * SKIN_SAMPLE_SPAN
                right = min(left + SKIN_SAMPLE_SPAN, field.columns)
                bottom = min(top + SKIN_SAMPLE_SPAN, field.rows)
                base = tuple(
                    _srgb_to_linear(channel)
                    for channel in iridophore_base(
                        (left + right) / (2 * field.columns),
                        (top + bottom) / (2 * field.rows),
                    )
                )
                reflections = _pigment_reflections(base)
                areas = self._sample_pigment_areas(field, spacing, (left, top, right, bottom))
                sample_area = (right - left) * (bottom - top)
                weights = {
                    pigment: SKIN_CONTRAST * coverage_gain * area / sample_area
                    for pigment, area in areas.items()
                }
                total_weight = sum(weights.values())
                # Compensation can exceed physical area. Normalise pigment shares
                # together rather than subtracting backing light or favouring a layer.
                normalisation = max(1.0, total_weight)
                colour = tuple(
                    _linear_to_srgb(
                        base[channel] * max(0.0, 1 - total_weight)
                        + sum(
                            reflections[pigment][channel] * weight / normalisation
                            for pigment, weight in weights.items()
                        )
                    )
                    for channel in range(3)
                )
                samples.set_at((sample_x, sample_y), colour)

        # Sharpen the integrated image rather than the discs. A small unsharp mask
        # strengthens pattern edges while leaving uniform regions unchanged.
        source = samples.copy()
        width, height = sample_size
        for y in range(height):
            for x in range(width):
                colour = source.get_at((x, y))
                totals = [0, 0, 0]
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        neighbour = source.get_at(
                            (max(0, min(width - 1, x + dx)), max(0, min(height - 1, y + dy)))
                        )
                        for channel in range(3):
                            totals[channel] += neighbour[channel]
                samples.set_at(
                    (x, y),
                    tuple(
                        max(0, min(255, round(value + SKIN_SHARPNESS * (value - total / 9))))
                        for value, total in zip(colour[:3], totals, strict=True)
                    ),
                )

        # Smooth enlargement blends sample boundaries into a continuous surface. This
        # is a visual approximation of viewing distance, not a biological optical model.
        skin = pygame.transform.smoothscale(samples, rectangle.size)
        self.surface.blit(skin, rectangle)

    @staticmethod
    def _sample_pigment_areas(
        field: ChromatophoreField,
        spacing: float,
        bounds: tuple[int, int, int, int],
    ) -> dict[Pigment, float]:
        """Integrate irregular disc intersections, including neighbours across sample edges.

        :param field: Read-only field containing fixed organ geometry.
        :param spacing: Display pixels per logical unit, positive.
        :param bounds: Sample rectangle in logical spacing units.
        :return: Covered area per pigment, in squared logical units.
        """
        left, top, right, bottom = bounds
        areas = dict.fromkeys(Pigment, 0.0)
        # Centres stay within their logical slots, and radii are below half a slot.
        # One neighbouring row/column therefore contains every possible contributor.
        for row in range(max(0, top - 1), min(field.rows, bottom + 1)):
            for column in range(max(0, left - 1), min(field.columns, right + 1)):
                index = row * field.columns + column
                cell, organ = field.cells[index], field.geometry[index]
                minimum_radius = min(MINIMUM_RADIUS / spacing, organ.radius_ratio)
                radius = minimum_radius + cell.expansion * (organ.radius_ratio - minimum_radius)
                areas[cell.pigment] += circle_rectangle_area(organ.x, organ.y, radius, bounds)
        return areas

    def _draw_pigment_legend(self) -> None:
        """Label the pigment controls; buttons retain their own colour indicators."""
        heading = self.title_font.render("Pigment levels", True, TEXT_COLOUR)
        self.surface.blit(heading, (760, 550))
        note = self.font.render("Click to cycle target strength", True, TEXT_COLOUR)
        self.surface.blit(note, (760, 585))
