"""Integrate pigment and structural reflection into a continuous Skin View.

Coverage, reflective backing and pigment transmission are combined in linear RGB,
then sharpened and enlarged for display. Rendering reads current model state
without changing targets, geometry or timing. View layout and controls stay in
view.py; the diagnostic disc renderer supplies the shared pigment palette and
minimum visible radius. Angular optics and circle intersections remain delegated
to reflection.py and coverage.py.
"""

from math import exp, isfinite
from types import MappingProxyType

import pygame

from chromatophore_simulator.chromatophore_renderer import MINIMUM_RADIUS, PIGMENT_COLOURS
from chromatophore_simulator.coverage import circle_rectangle_area
from chromatophore_simulator.model import ChromatophoreField, Pigment
from chromatophore_simulator.reflection import (
    DEFAULT_REFLECTION_RESPONSES,
    REFERENCE_REFLECTION_COLOUR,
    REFLECTOR_CENTRES,
    AngularReflection,
    ReflectionSettings,
    reflection_responses,
)

SKIN_COLOUR = (235, 232, 220)
IRIDOPHORE_COLOUR = REFERENCE_REFLECTION_COLOUR

# A lower reference fraction keeps a distributed layer restrained: the previous
# 0.28 fraction was confined to three small patches, with mostly pale gaps.
IRIDOPHORE_STRENGTH = 0.14
IRIDOPHORE_REGION_RADIUS = 0.24
IRIDOPHORE_PATCHES = tuple(
    (x, y, IRIDOPHORE_REGION_RADIUS, IRIDOPHORE_REGION_RADIUS) for x, y in REFLECTOR_CENTRES
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

SKIN_SAMPLE_SPAN = 4  # Integrate four logical spacings per sample, including partial edges.
SKIN_CONTRAST = 2.0  # Display coverage boost, applied after fixed layout calibration.
SKIN_REFERENCE_RADIUS_RATIO = 0.45  # Preserve the pre-morphology layout's pigment density.
SKIN_SHARPNESS = 0.75  # Gentle edge definition without the former strong colour overshoot.


def iridophore_base(
    x: float,
    y: float,
    angular_responses: tuple[AngularReflection, ...] = DEFAULT_REFLECTION_RESPONSES,
) -> tuple[int, ...]:
    """Mix local structural reflection into the pale backing before pigment filtering.

    Overlapping regions are averaged by spatial weight. Normalising the weights
    avoids bright grid seams, gaps at the edges and accumulation from overlaps.
    Reflection strength is capped so this remains a bounded mixture.

    :param x: Normalised horizontal coordinate in [0, 1].
    :param y: Normalised vertical coordinate in [0, 1].
    :param angular_responses: One precomputed angular response per fixed patch.
    :return: Three integer sRGB channels in [0, 255].
    :raises ValueError: If coordinates or response count are invalid.
    """
    if not all(isfinite(value) and 0 <= value <= 1 for value in (x, y)):
        raise ValueError("Skin coordinates must be finite and between 0 and 1")
    if len(angular_responses) != len(IRIDOPHORE_PATCHES):
        raise ValueError("Angular response count must match iridophore patches")

    # Gaussian distance weights make nearby reflective regions contribute more
    # than distant ones. Dividing offsets by each region's radius expresses
    # distance relative to its extent, independent of the display resolution.
    weights = tuple(
        exp(-2 * (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2))
        for cx, cy, rx, ry in IRIDOPHORE_PATCHES
    )

    # Normalising by the local weight sum keeps coverage continuous at the skin
    # edges, where fewer regions contribute. The fixed overlapping layout ensures
    # a positive sum throughout the supported coordinate range.
    total_weight = sum(weights)

    # Blend each region's bounded colour contribution, rather than selecting a
    # winner: nearby orientations then transition smoothly as the angles change.
    amounts = tuple(
        weight / total_weight * max(0.0, min(1.0, IRIDOPHORE_STRENGTH * response.strength))
        for weight, response in zip(weights, angular_responses, strict=True)
    )

    # Each amount replaces a share of the pale backing with reflected colour.
    # Their sum cannot exceed 1, so this stays a bounded mixture rather than
    # adding light indefinitely. This backing-colour approximation uses sRGB;
    # the subsequent pigment mixture is calculated in linear light.
    return tuple(
        round(
            backing
            + sum(
                amount * (response.colour[channel] - backing)
                for amount, response in zip(amounts, angular_responses, strict=True)
            )
        )
        for channel, backing in enumerate(SKIN_COLOUR)
    )


def _srgb_to_linear(channel: int) -> float:
    """Decode one sRGB channel to relative light intensity.

    :param channel: Display channel in the inclusive range 0 to 255.
    :return: Linear intensity in the inclusive range 0 to 1.
    """
    # Display channel values are non-linear: averaging them directly would not
    # average light intensity. Decode the sRGB transfer curve before mixing;
    # its low-value linear segment avoids a steep power curve near black.
    value = channel / SRGB_CHANNEL_MAXIMUM
    if value <= SRGB_LINEAR_THRESHOLD:
        return value / SRGB_LINEAR_SCALE
    return ((value + SRGB_OFFSET) / SRGB_SCALE) ** SRGB_EXPONENT


def _linear_to_srgb(value: float) -> int:
    """Encode linear light intensity as a clamped display channel.

    :param value: Relative linear light intensity, normally between 0 and 1.
    :return: Integer sRGB channel in the inclusive range 0 to 255.
    """
    # Reverse the decoding only after light contributions have been combined.
    # Clamp to the displayable range before applying the transfer curve, then
    # round to an integer channel for storage in the image surface.
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
    # Transmission is channel-specific and already represents a round trip
    # through the pigment. Mix that filtered backing share with the pigment's
    # own reflected colour; do not square transmission or multiply by expansion
    # here, because the coefficients include the round trip and coverage is
    # handled separately by the sampled disc areas.
    return {
        pigment: tuple(
            _srgb_to_linear(colour) * (1 - transmission) + light * transmission
            for colour, light, transmission in zip(
                PIGMENT_COLOURS[pigment], backing, PIGMENT_TRANSMISSION[pigment], strict=True
            )
        )
        for pigment in Pigment
    }


def _skin_coverage_gain(field: ChromatophoreField) -> float:
    """Calibrate fixed morphology against the former regular layout's maximum area.

    Smaller organs need greater coverage compensation in the integrated view.
    Using maximum rather than current radii avoids brightness pumping as organs
    move. A single global factor preserves local size and pigment differences.
    The circle-area factor pi cancels from the ratio of the two area totals.

    :param field: Non-empty field with factory-generated positive maximum radii.
    :return: Dimensionless multiplier for integrated pigment coverage.
    """
    # Compare total maximum disc area with a reference population of the same
    # size. Both areas contain pi, so only squared radii are needed. Using one
    # field-wide gain retains local size differences instead of equalising organs.
    maximum_area = sum(organ.radius_ratio**2 for organ in field.geometry)
    return len(field.geometry) * SKIN_REFERENCE_RADIUS_RATIO**2 / maximum_area


def draw_skin(
    surface: pygame.Surface,
    rectangle: pygame.Rect,
    field: ChromatophoreField,
    spacing: float,
    reflection: ReflectionSettings,
) -> None:
    """Integrate pigment coverage directly, avoiding pixel-grid sampling artefacts.

    :param surface: Destination surface, readied by the coordinating view.
    :param reflection: Validated viewing and light directions.
    :param rectangle: Occupied grid bounds in the display surface, in pixels.
    :param field: Current cell states, read without mutation.
    :param spacing: Pixels per logical target spacing in the detailed view.
    """
    # Ceiling division keeps a final partial sample when the field dimensions
    # are not multiples of the sample span. Sampling in logical cell units
    # separates pigment integration from the resolution of the display surface.
    sample_size = (
        max(1, (field.columns + SKIN_SAMPLE_SPAN - 1) // SKIN_SAMPLE_SPAN),
        max(1, (field.rows + SKIN_SAMPLE_SPAN - 1) // SKIN_SAMPLE_SPAN),
    )

    samples = pygame.Surface(sample_size)

    # Geometry calibration and angular responses are shared by all samples in
    # this frame. Only spatial blending and current pigment coverage vary below.
    coverage_gain = _skin_coverage_gain(field)
    angular_responses = reflection_responses(reflection)

    for sample_y in range(sample_size[1]):
        for sample_x in range(sample_size[0]):
            # Clip the final sample to the actual field edge. Its true area,
            # rather than a full sample's area, will be used to calculate coverage.
            left = sample_x * SKIN_SAMPLE_SPAN
            top = sample_y * SKIN_SAMPLE_SPAN
            right = min(left + SKIN_SAMPLE_SPAN, field.columns)
            bottom = min(top + SKIN_SAMPLE_SPAN, field.rows)

            # Evaluate the reflective backing at the sample centre, normalised
            # to the whole field. This approximates the smooth backing within
            # the sample; pigment disc intersections are integrated analytically.
            # Decode the backing to linear light before combining pigment shares.
            base = tuple(
                _srgb_to_linear(channel)
                for channel in iridophore_base(
                    (left + right) / (2 * field.columns),
                    (top + bottom) / (2 * field.rows),
                    angular_responses,
                )
            )
            reflections = _pigment_reflections(base)
            areas = sample_pigment_areas(field, spacing, (left, top, right, bottom))
            sample_area = (right - left) * (bottom - top)

            # Area/sample_area is geometric coverage. The fixed morphology gain
            # and presentation contrast boost make the small, irregular discs
            # read as an integrated pattern without changing the organs themselves.
            weights = {
                pigment: SKIN_CONTRAST * coverage_gain * area / sample_area
                for pigment, area in areas.items()
            }
            total_weight = sum(weights.values())

            # Compensation can exceed physical area. Normalise pigment shares
            # together rather than subtracting backing light or favouring a layer.
            normalisation = max(1.0, total_weight)

            # Below full coverage, uncovered area shows the backing directly.
            # At or above full coverage, pigment shares are normalised to sum
            # to 1 and the direct backing share becomes zero. Filtered backing
            # remains present within each pigment's reflection in either case.
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
    # Read every neighbourhood from the unmodified image. Reading partly
    # sharpened pixels would make the result depend on traversal direction.
    source = samples.copy()
    width, height = sample_size
    for y in range(height):
        for x in range(width):
            colour = source.get_at((x, y))
            totals = [0, 0, 0]

            # Average a 3 x 3 neighbourhood for each RGB channel. Repeat edge
            # pixels when the neighbourhood extends beyond the image, avoiding
            # dark borders from treating missing neighbours as black.
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    neighbour = source.get_at(
                        (max(0, min(width - 1, x + dx)), max(0, min(height - 1, y + dy)))
                    )
                    for channel in range(3):
                        totals[channel] += neighbour[channel]

            # Add a fraction of the difference from the local mean. Flat colours
            # have zero difference; edges are strengthened. Clamp any overshoot
            # because sharpening is display enhancement, not extra reflected light.
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
    surface.blit(skin, rectangle)


def sample_pigment_areas(
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

            # Convert the diagnostic minimum dot radius from display pixels to
            # logical units so both rendering modes use the same visible disc.
            # Cap it for small organs, then interpolate radius using current
            # expansion; targets are not used to predict future coverage.
            minimum_radius = min(MINIMUM_RADIUS / spacing, organ.radius_ratio)
            radius = minimum_radius + cell.expansion * (organ.radius_ratio - minimum_radius)

            # Add only the part of this disc inside the sample. Group by pigment
            # so the later light mixture can use each pigment's own transmission.
            areas[cell.pigment] += circle_rectangle_area(organ.x, organ.y, radius, bounds)
    return areas
