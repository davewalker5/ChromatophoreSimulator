"""Generate patterns that change over time by updating each cell's target expansion.

A dynamic pattern is a set of instructions for how expanded each chromatophore
should be at a particular moment. DynamicController generates those targets;
it does not draw the field or directly change the cells' current sizes.

DynamicController.__init__() prepares the selected display, starts its clocks,
and records each cell's horizontal position and distance from the field's centre.
It calls _neighbour_arrivals() to calculate when a signal spreading from the
central cell would reach each neighbour. Those arrival times are used by Local
Excitation and also determine how long it waits before repeating.

targets_at() works out the expansion targets for a given point in the sequence.
Travelling waves and moving bands shift areas of expansion across the field.
Radial pulses move expansion outwards in a ring. Flash alternates the whole field
between expansion and contraction. Local excitation starts at a central cell
and spreads through its neighbours, with each cell activating for a fixed time
after the signal reaches it. Changing Mottle uses targets_at() to choose a fresh
random mottle every six display seconds. The targets stay fixed between changes,
allowing the existing cells to animate smoothly towards each new arrangement.

advance() moves the clocks forward by the time supplied by the field, which calls
it in small, fixed simulation steps. Display speed controls how quickly the
pattern progresses; response delay makes cells follow an earlier point in that
sequence. advance() remembers speed changes, works out the appropriate earlier
point, and calls targets_at() to generate its targets. It returns None while the
initial delay is still pending, leaving the cells at their starting sizes.

Outside this module, ChromatophoreField.update() passes the targets returned by
advance() to the existing chromatophores. Chromatophore.update() then makes them
expand or contract using their own current sizes and the configured response
rates. Slow responses can therefore soften or lag behind a fast-moving pattern.
Both graphical views show those same evolving cell states. Selecting a static
pattern stops the controller; holding the display keeps the cells at their
current sizes.
"""

from bisect import bisect_right
from collections import deque
from enum import Enum
from math import cos, hypot, isfinite, pi
from random import Random

from chromatophore_simulator.patterns import Pattern, generate_targets

DYNAMIC_STEP = 1 / 60  # Fixed simulation step, in seconds, for reproducible animation.
# These are the pattern timings at normal speed. Doubling display speed makes
# each pattern run twice as fast, but does not change cell movement speed or delay.
TRAVEL_PERIOD = 16.0
FLASH_PERIOD = 4.0
MOTTLE_PERIOD = 6.0  # Time between fresh target patterns at normal display speed.
EXCITATION_HOP_SECONDS = 0.12
EXCITATION_HOLD_SECONDS = 4.0
EXCITATION_REST_SECONDS = 2.0


class DynamicDisplay(Enum):
    TRAVELLING_WAVE = "Travelling wave"
    RADIAL_PULSE = "Radial pulse"
    FLASH = "Flash"
    MOVING_BANDS = "Moving bands"
    LOCAL_EXCITATION = "Local excitation"
    CHANGING_MOTTLE = "Changing mottle"


class DynamicController:
    """Generate evolving targets using a simulation clock and optional signal lag."""

    def __init__(
        self, display: DynamicDisplay, rows: int, columns: int, random_source: Random | None = None
    ) -> None:
        """Prepare a display and its spatial coordinates.

        :param display: Animated display to run.
        :param rows: Positive integer field height.
        :param columns: Positive integer field width.
        :param random_source: Optional seeded generator for reproducible mottle sequences.
        :raises ValueError: If the display or dimensions are invalid.
        """
        if not isinstance(display, DynamicDisplay):
            raise ValueError("Display must be a member of DynamicDisplay")
        if any(type(size) is not int or size <= 0 for size in (rows, columns)):
            raise ValueError("Display dimensions must be positive integers")

        self.display = display
        self.rows = rows
        self.columns = columns
        self._mottle_seed = (
            (random_source if random_source is not None else Random()).getrandbits(64)
            if display is DynamicDisplay.CHANGING_MOTTLE
            else 0
        )
        self._mottle_index = -1
        self._mottle_targets: tuple[float, ...] = ()

        # Track both how long the simulation has run and how far the pattern has
        # progressed. At double speed, the pattern covers two seconds of its sequence
        # in one simulation second. A speed change continues from its current position.
        self.elapsed = 0.0
        self.phase_seconds = 0.0
        self.speed = 1.0

        # Remember when each speed change happened, where the pattern had reached,
        # and its new speed. This lets us work out what the pattern looked like earlier
        # when cells are following it with a response delay.
        self._segment_times = [0.0]
        self._segments = [(0.0, 1.0)]

        # For each cell, remember how far across the field it is and how far it is
        # from the centre. Horizontal position runs from 0 at the left to 1 at the right.
        # Centre distances use the same ruler vertically and horizontally, so circles
        # stay circular on rectangular fields. A minimum ruler length of one also lets
        # us handle fields with only one row or column.
        scale = max(rows - 1, columns - 1, 1)
        self._positions = tuple(
            (
                column / max(columns - 1, 1),
                hypot(row - (rows - 1) / 2, column - (columns - 1) / 2) / scale,
            )
            for row in range(rows)
            for column in range(columns)
        )

        self._arrival = self._neighbour_arrivals()

        # Allow enough time for the signal to reach the farthest cell and finish
        # asking it to expand, then wait before repeating. Slow cells may still be
        # contracting during this rest period.
        self._excitation_period = (
            max(self._arrival) + EXCITATION_HOLD_SECONDS + EXCITATION_REST_SECONDS
        )

    def _neighbour_arrivals(self) -> tuple[float, ...]:
        """Compute signal arrival times by propagating through four-connected neighbours.

        :return: Earliest arrival at each cell, in display-phase seconds.
        """
        source = (self.rows // 2, self.columns // 2)

        # Start the signal at one central cell. Where there are two middle rows or
        # columns, choose the lower or right-hand one. Mark all other cells as unreached
        # until we have worked out when the signal gets to them.
        arrivals = [-1.0] * (self.rows * self.columns)
        arrivals[source[0] * self.columns + source[1]] = 0.0
        queue = deque([source])

        # Spread out one neighbour at a time: first the centre's neighbours, then
        # their neighbours, and so on. Each step adds the same travel time. We only
        # move up, down, left or right, so the spreading region has a diamond shape.
        while queue:
            row, column = queue.popleft()
            arrival = arrivals[row * self.columns + column] + EXCITATION_HOP_SECONDS
            for next_row, next_column in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            ):
                if 0 <= next_row < self.rows and 0 <= next_column < self.columns:
                    index = next_row * self.columns + next_column
                    if arrivals[index] < 0:
                        # Record the first arrival and add this neighbour to the cells
                        # that will pass the signal on. A cell already reached needs no
                        # second visit: taking a longer route cannot reach it sooner.
                        arrivals[index] = arrival
                        queue.append((next_row, next_column))
        return tuple(arrivals)

    def advance(self, seconds: float, delay: float) -> tuple[float, ...] | None:
        """Advance the signal and return its delayed targets.

        :param seconds: Finite non-negative simulation time step.
        :param delay: Finite non-negative signal lag in simulation seconds.
        :return: Targets, or None while initial signal latency is still pending.
        :raises ValueError: If time, delay or speed is invalid.
        """
        if not isfinite(seconds) or seconds < 0:
            raise ValueError("Seconds must be finite and non-negative")
        if not isfinite(delay) or delay < 0:
            raise ValueError("Delay must be finite and non-negative")
        if not isfinite(self.speed) or self.speed <= 0:
            raise ValueError("Speed must be finite and positive")

        # If speed has changed, save where and when that happened before moving on.
        # Between speed changes we can calculate the pattern's progress directly,
        # so there is no need to save a picture of the field for every frame.
        if self.speed != self._segments[-1][1]:
            self._segment_times.append(self.elapsed)
            self._segments.append((self.phase_seconds, self.speed))

        self.elapsed += seconds
        self.phase_seconds += seconds * self.speed

        # Make the cells follow an earlier point in the pattern. For example, with
        # a half-second delay they follow what the pattern was doing half a second ago.
        # Before that much time has passed, leave their starting sizes alone.
        signal_time = self.elapsed - delay
        if signal_time < 0:
            return None

        # Find the most recent speed change at or before the time we want to show.
        # That tells us which speed was in effect at that point in the pattern's history.
        index = bisect_right(self._segment_times, signal_time) - 1
        start_phase, speed = self._segments[index]

        # Start where the pattern was at that speed change and add the progress made
        # since then. Using the speed from that time keeps delayed movement correct,
        # even if the user has changed the speed again since.
        phase = start_phase + (signal_time - self._segment_times[index]) * speed
        return self.targets_at(phase)

    def targets_at(self, phase_seconds: float) -> tuple[float, ...]:
        """Sample the waveform at a specified display-phase time.

        :param phase_seconds: Finite non-negative phase, independent of wall-clock time.
        :return: Row-major targets in [0, 1].
        :raises ValueError: If phase is invalid.
        """
        if not isfinite(phase_seconds) or phase_seconds < 0:
            raise ValueError("Phase must be finite and non-negative")

        if self.display is DynamicDisplay.CHANGING_MOTTLE:
            # Hold each random target for several seconds while the cells move towards
            # it, then choose a new one. Reuse the static mottle algorithm for its patches.
            index = int(phase_seconds / MOTTLE_PERIOD)
            if index != self._mottle_index:
                # Derive a seed from the sequence and interval, so looking backwards
                # through response delay reproduces the same pattern. Cache only the
                # requested pattern: long-running displays do not accumulate images.
                source = Random(f"{self._mottle_seed}:{index}")
                self._mottle_targets = generate_targets(
                    Pattern.RANDOM_MOTTLE, self.rows, self.columns, source
                )
                self._mottle_index = index
            return self._mottle_targets

        # Work out how far through the current repetition we are: zero means the
        # start, and values approaching one mean almost finished. Once a repetition
        # ends, begin the next one without resetting the overall simulation time.
        phase = (phase_seconds / TRAVEL_PERIOD) % 1.0
        if self.display is DynamicDisplay.FLASH:
            # Ask every cell to expand for the first half of each flash, then contract
            # for the second half. These are target changes; the cells still take time
            # to move, so slow response rates produce a gentler flash.
            return (float(phase_seconds % FLASH_PERIOD < FLASH_PERIOD / 2),) * len(self._positions)
        if self.display is DynamicDisplay.LOCAL_EXCITATION:
            local_time = phase_seconds % self._excitation_period
            # Ask a cell to expand once the spreading signal reaches it, and keep
            # asking for the same fixed duration. Before arrival, and after that time
            # runs out, ask it to contract. Farther cells therefore activate later.
            return tuple(
                float(0 <= local_time - arrival < EXCITATION_HOLD_SECONDS)
                for arrival in self._arrival
            )

        targets = []
        for x, radius in self._positions:
            if self.display is DynamicDisplay.TRAVELLING_WAVE:
                # Move one band from just outside the left edge to just outside the
                # right edge. Measure each cell's distance from the band's centre:
                # zero is the centre, and one is the edge, a quarter-field-width away.
                distance = abs(x - (-0.25 + 1.5 * phase)) / 0.25

                # Ask cells at the centre to expand fully, with progressively less
                # expansion towards either edge. Outside the band, keep them contracted.
                # The curved fall-off makes the band's edges soft rather than abrupt.
                value = (1 + cos(pi * distance)) / 2 if distance < 1 else 0.0
            elif self.display is DynamicDisplay.RADIAL_PULSE:
                # Move a ring outwards from the centre. Cells on the ring expand most;
                # those inside or outside it expand less as their distance increases.
                # Beyond the ring's soft edges they contract again, so the centre fades
                # while the expanding ring reaches cells farther away.
                distance = abs(radius - phase) / 0.2
                value = (1 + cos(pi * distance)) / 2 if distance < 1 else 0.0
            else:
                # Lay two repeating bands across the field, gradually alternating
                # between expanded and contracted cells. Move the whole arrangement
                # rightwards over time. After moving half the field's width, the next
                # band occupies the previous one's position and the pattern repeats.
                # Convert the wave's height into a target between contracted and expanded.
                value = (1 + cos(2 * pi * (2 * x - phase))) / 2
            targets.append(value)
        return tuple(targets)
