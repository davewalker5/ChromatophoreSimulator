"""Rendering-independent chromatophore state, with time measured in seconds."""

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from random import Random

from chromatophore_simulator.dynamics import DYNAMIC_STEP, DynamicController, DynamicDisplay
from chromatophore_simulator.patterns import Pattern, generate_targets

DEFAULT_ROWS = 50
DEFAULT_COLUMNS = 50


class Pigment(Enum):
    """Pigment identity; display colours belong to the renderer, not the model."""

    YELLOW = "Yellow"
    RED = "Red"
    BROWN = "Brown"
    BLACK = "Black"


# Repeat this tile across the field so all four pigments occur in each 2 × 2 patch.
# Alternating positions keep every organ visible without a layer drawing order.
PIGMENT_TILE = ((Pigment.YELLOW, Pigment.RED), (Pigment.BROWN, Pigment.BLACK))


def _validate_time(value: float) -> None:
    """Validate a duration measured in seconds.

    :param value: Finite, non-negative duration.
    :raises ValueError: If the duration is negative or non-finite.
    """
    if not isfinite(value) or value < 0:
        raise ValueError("Seconds must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ResponseParameters:
    """Rates in expansion units per second and delay in simulation seconds."""

    # Increase in expansion per simulation second while moving towards a larger target.
    # Expansion spans 0 to 1, so 0.25/s takes four seconds for a full expansion.
    expansion_rate: float = 0.25

    # Decrease in expansion per simulation second while moving towards a smaller target.
    # Both rates are read on every update, so changing them affects movement immediately.
    contraction_rate: float = 0.25

    # Simulation seconds to hold the current size after receiving a changed target.
    # Copied into each cell's countdown by set_target; changing this setting affects
    # future target changes, not countdowns already running. Zero means no waiting.
    response_delay: float = 0.0

    def __post_init__(self) -> None:
        """Reject non-positive/non-finite rates and negative/non-finite delay.

        :raises ValueError: If a rate or delay is invalid.
        """
        for rate in (self.expansion_rate, self.contraction_rate):
            if not isfinite(rate) or rate <= 0:
                raise ValueError("Response rates must be finite and greater than zero")
        _validate_time(self.response_delay)


def _validate_expansion(value: float) -> None:
    """Validate a normalised expansion value.

    :param value: Requested expansion in the inclusive range [0, 1].
    :raises ValueError: If the value is non-finite or outside the range.
    """
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("Expansion must be finite and between 0 and 1")


@dataclass(slots=True)
class Chromatophore:
    """One pigment organ; its grid position is stored by the owning field."""

    expansion: float = 0.0
    target_expansion: float = 0.0

    # Pigment stays the same during transitions; only its visible radius changes.
    # Brown remains the default for individually constructed cells.
    pigment: Pigment = Pigment.BROWN

    _delay_remaining: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Reject invalid initial expansion, target or pigment values.

        :raises ValueError: If an expansion or pigment is invalid.
        """
        _validate_expansion(self.expansion)
        _validate_expansion(self.target_expansion)
        if not isinstance(self.pigment, Pigment):
            raise ValueError("Pigment must be a member of Pigment")

    def set_target(self, expansion: float, response_delay: float = 0.0) -> None:
        """Change the target without immediately changing visible expansion.

        :param expansion: Normalised target in [0, 1].
        :param response_delay: Non-negative seconds to wait before moving.
        :raises ValueError: If expansion or delay is invalid.
        """
        _validate_expansion(expansion)
        _validate_time(response_delay)
        if expansion == self.target_expansion:
            return
        self.target_expansion = expansion
        self._delay_remaining = response_delay if expansion != self.expansion else 0.0

    def update(self, elapsed_seconds: float, response: ResponseParameters) -> None:
        """Wait out latency, then move towards the target without overshooting.

        A changed target holds the current size during its delay. Repeated targets
        do not restart that delay. Rate changes affect the next movement update.

        :param elapsed_seconds: Finite, non-negative simulation time to advance.
        :param response: Separate expansion and contraction rates.
        :raises ValueError: If elapsed time is invalid.
        """
        _validate_time(elapsed_seconds)

        # Consume the waiting portion first, without letting the countdown go negative.
        # If the delay expires partway through this update, only the leftover time
        # contributes to movement (e.g. 0.1 s elapsed minus 0.04 s waiting = 0.06 s moving).
        waiting_seconds = min(elapsed_seconds, self._delay_remaining)
        self._delay_remaining -= waiting_seconds
        moving_seconds = elapsed_seconds - waiting_seconds

        # The sign tells us which way to move: positive means expand, negative means
        # contract. Read the current rate each update so speed changes apply immediately.
        difference = self.target_expansion - self.expansion
        rate = response.expansion_rate if difference > 0 else response.contraction_rate

        # Rate is measured in expansion units per second, so multiplying by seconds
        # gives this update's allowed change. At 0.25/s, 0.02 s allows a change of 0.005.
        # Using elapsed time rather than a fixed step keeps speed independent of FPS.
        maximum_change = rate * moving_seconds

        # Snap to the target when the remaining distance fits within this step. This
        # prevents overshoot and ensures we finish exactly at the requested expansion.
        # Otherwise take the full allowed step in the required direction; while waiting,
        # maximum_change is zero, so the current expansion remains unchanged.
        if abs(difference) <= maximum_change:
            self.expansion = self.target_expansion
        elif difference > 0:
            self.expansion += maximum_change
        else:
            self.expansion -= maximum_change


class ChromatophoreField:
    """A regular row-major grid, with the origin at the upper-left corner."""

    def __init__(
        self,
        rows: int = DEFAULT_ROWS,
        columns: int = DEFAULT_COLUMNS,
        response: ResponseParameters = ResponseParameters(),
    ) -> None:
        """Create contracted cells with four pigments alternating at fixed positions.

        :param rows: Positive number of rows.
        :param columns: Positive number of columns.
        :param response: Validated response settings; may be replaced during a run.
        :raises ValueError: If either dimension is not a positive integer.
        """
        if any(type(size) is not int or size <= 0 for size in (rows, columns)):
            raise ValueError("Field dimensions must be positive integers")
        self.rows = rows
        self.columns = columns
        self.response = response

        # Use row/column parity rather than flat index parity, so odd-width fields
        # retain the same spatial tile. Each cell still owns its own state and delay.
        self.cells = tuple(
            Chromatophore(pigment=PIGMENT_TILE[row % 2][column % 2])
            for row in range(rows)
            for column in range(columns)
        )
        self.target_description = "Contracted"
        self.dynamic: DynamicController | None = None
        self._dynamic_remainder = 0.0

    def start_dynamic(self, display: DynamicDisplay, random_source: Random | None = None) -> None:
        """Start a display from its initial phase without changing current sizes.

        :param display: Animated display to select or restart.
        :param random_source: Optional seeded generator for dynamic mottle.
        :raises ValueError: If the display is invalid.
        """
        controller = DynamicController(display, self.rows, self.columns, random_source)
        self.hold()
        self.dynamic = controller
        self.target_description = display.value

    def hold(self) -> None:
        """Stop animation targets and hold every cell at its current expansion."""
        self.dynamic = None
        self._dynamic_remainder = 0.0
        for cell in self.cells:
            cell.set_target(cell.expansion, 0.0)
        self.target_description = "Held"

    def set_targets(self, targets: tuple[float, ...]) -> None:
        """Assign a complete target field without replacing cells or current sizes.

        Validate all targets before mutation so invalid input leaves the field intact.
        Each changed target starts that cell's configured response delay.

        :param targets: Row-major expansion values, one per cell.
        :raises ValueError: If the count or any expansion value is invalid.
        """
        if len(targets) != len(self.cells):
            raise ValueError("Target count must match the number of cells")
        for target in targets:
            _validate_expansion(target)
        self.dynamic = None
        for cell, target in zip(self.cells, targets, strict=True):
            cell.set_target(target, self.response.response_delay)
        self.target_description = "Custom"

    def apply_pattern(self, pattern: Pattern, random_source: Random) -> None:
        """Calculate a pattern once, then let normal updates animate towards it.

        :param pattern: Predefined pattern to select.
        :param random_source: Caller-owned random generator for mottle.
        :raises ValueError: If the pattern is invalid.
        """
        self.set_targets(generate_targets(pattern, self.rows, self.columns, random_source))
        self.target_description = pattern.value

    def set_expansion(self, expansion: float) -> None:
        """Set every cell's target expansion, preserving its current state.

        :param expansion: Normalised target in [0, 1].
        :raises ValueError: If expansion is invalid; no cells are changed.
        """
        _validate_expansion(expansion)
        self.dynamic = None
        for cell in self.cells:
            cell.set_target(expansion, self.response.response_delay)
        self.target_description = f"Uniform {expansion:.0%}"

    def randomise(self, random_source: Random) -> None:
        """Assign independent uniformly distributed targets in [0, 1).

        :param random_source: Random generator, optionally seeded by the caller.
        """
        self.dynamic = None
        for cell in self.cells:
            cell.set_target(random_source.random(), self.response.response_delay)
        self.target_description = "Randomise"

    def update(self, elapsed_seconds: float) -> None:
        """Advance independent cell delays and movement using current rates.

        :param elapsed_seconds: Finite, non-negative time since the previous update.
        :raises ValueError: If elapsed time is negative or non-finite.
        """
        _validate_time(elapsed_seconds)
        if self.dynamic is not None:
            # Fixed-size substeps make both signal sampling and cell response stable
            # across frame rates; retain the fractional remainder for the next frame.
            self._dynamic_remainder += elapsed_seconds
            steps = int((self._dynamic_remainder + 1e-12) / DYNAMIC_STEP)
            self._dynamic_remainder = max(0.0, self._dynamic_remainder - steps * DYNAMIC_STEP)
            for _ in range(steps):
                targets = self.dynamic.advance(DYNAMIC_STEP, self.response.response_delay)
                if targets is not None:
                    for cell, target in zip(self.cells, targets, strict=True):
                        cell.set_target(target, 0.0)
                for cell in self.cells:
                    cell.update(DYNAMIC_STEP, self.response)
            return
        for cell in self.cells:
            cell.update(elapsed_seconds, self.response)
