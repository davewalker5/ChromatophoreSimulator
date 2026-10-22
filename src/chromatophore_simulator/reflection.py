"""Angle-dependent iridophore response for a fixed, planar optical cross-section."""

from dataclasses import dataclass
from math import cos, exp, isfinite, radians, sin, sqrt

MAXIMUM_ANGLE_DEGREES = 60.0
ANGLE_PRESETS = (-60.0, -45.0, -30.0, -15.0, 0.0, 15.0, 30.0, 45.0, 60.0)
PATCH_NORMAL_DEGREES = (-12.0, 0.0, 15.0)
REFLECTOR_SPREAD_DEGREES = 22.0
DIFFUSE_REFLECTION_FRACTION = 0.2
WATER_REFRACTIVE_INDEX = 1.33
EFFECTIVE_REFRACTIVE_INDEX = 1.5
NORMAL_PEAK_WAVELENGTH_NM = 500.0
VISIBLE_FADE_START_NM = 360.0
VISIBLE_FADE_END_NM = 400.0
# Illustrative sRGB colour ramp, anchored to the existing normal-view palette.
# This is not spectral integration against a measured illumination spectrum.
REFERENCE_REFLECTION_COLOUR = (126, 179, 205)
WAVELENGTH_COLOURS = (
    (380.0, (137, 105, 170)),
    (420.0, (142, 113, 208)),
    (460.0, (106, 143, 215)),
    (500.0, REFERENCE_REFLECTION_COLOUR),
)


@dataclass(frozen=True, slots=True)
class ReflectionSettings:
    """Outward camera/light directions in degrees from the flat skin normal.

    Both signed directions lie in the same plane: positive points to the right.
    They adjust reflection only, not perspective, organ positions or illumination
    of the diagnostic discs. Zero/zero preserves the previous appearance.
    """

    view_angle: float = 0.0
    light_angle: float = 0.0

    def __post_init__(self) -> None:
        """Reject non-finite or unsupported camera/light angles before use.

        :raises ValueError: If either angle is outside [-60, 60] degrees.
        """
        if any(
            isinstance(angle, bool)
            or not isinstance(angle, (int, float))
            or not isfinite(angle)
            or abs(angle) > MAXIMUM_ANGLE_DEGREES
            for angle in (self.view_angle, self.light_angle)
        ):
            raise ValueError("Reflection angles must be finite and between -60 and 60 degrees")


@dataclass(frozen=True, slots=True)
class AngularReflection:
    """Illustrative reflected sRGB colour and dimensionless patch strength multiplier."""

    colour: tuple[float, ...]
    strength: float


def _wavelength_colour(wavelength: float) -> tuple[float, ...]:
    """Interpolate the display ramp, clamping wavelengths outside its endpoints.

    :param wavelength: Reflected peak wavelength in nanometres.
    :return: Three sRGB channels in [0, 255], without premature rounding.
    """
    if wavelength <= WAVELENGTH_COLOURS[0][0]:
        return WAVELENGTH_COLOURS[0][1]
    for (lower, colour_a), (upper, colour_b) in zip(WAVELENGTH_COLOURS, WAVELENGTH_COLOURS[1:]):
        if wavelength <= upper:
            fraction = (wavelength - lower) / (upper - lower)
            return tuple(a + fraction * (b - a) for a, b in zip(colour_a, colour_b, strict=True))
    return WAVELENGTH_COLOURS[-1][1]


def reflection_responses(
    settings: ReflectionSettings = ReflectionSettings(),
) -> tuple[AngularReflection, ...]:
    """Calculate fixed patch responses once per render, before pigment filtering.

    The half-vector selects reflector normals facing the light/camera pair. A
    broad lobe approximates dispersed plate orientations; each patch's lobe is
    normalised to the previous zero-angle strength. The angle between incident
    and reflected directions controls a Snell/Bragg-inspired wavelength shift.
    A smooth visibility fade suppresses peaks moving outside the visible range.

    :param settings: Validated signed camera and light angles, in degrees.
    :return: One bounded colour/strength response per preferred patch orientation.
    """
    half_angle = (settings.view_angle + settings.light_angle) / 2
    incidence = radians((settings.view_angle - settings.light_angle) / 2)
    index_ratio = WATER_REFRACTIVE_INDEX / EFFECTIVE_REFRACTIVE_INDEX
    wavelength = NORMAL_PEAK_WAVELENGTH_NM * sqrt(max(0.0, 1 - (index_ratio * sin(incidence)) ** 2))
    colour = _wavelength_colour(wavelength)
    visible = max(
        0.0,
        min(
            1.0,
            (wavelength - VISIBLE_FADE_START_NM) / (VISIBLE_FADE_END_NM - VISIBLE_FADE_START_NM),
        ),
    )
    illumination = max(0.0, cos(radians(settings.light_angle)))
    responses = []
    for normal in PATCH_NORMAL_DEGREES:
        lobe = DIFFUSE_REFLECTION_FRACTION + (1 - DIFFUSE_REFLECTION_FRACTION) * exp(
            -0.5 * ((half_angle - normal) / REFLECTOR_SPREAD_DEGREES) ** 2
        )
        reference = DIFFUSE_REFLECTION_FRACTION + (1 - DIFFUSE_REFLECTION_FRACTION) * exp(
            -0.5 * (normal / REFLECTOR_SPREAD_DEGREES) ** 2
        )
        responses.append(AngularReflection(colour, lobe / reference * illumination * visible))
    return tuple(responses)


DEFAULT_REFLECTION_RESPONSES = reflection_responses()
