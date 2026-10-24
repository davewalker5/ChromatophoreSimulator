"""Calculate how viewing and light angles change the simulated iridophore reflection.

Skin View represents the reflective layer beneath the chromatophores using 49
overlapping regions. Their preferred reflector directions vary smoothly across
the skin, allowing a broad sheen to change as the angles move rather than showing
only a few isolated coloured spots. These directions describe an illustrative
distribution of reflective platelets, not actual bumps or tilts in the skin surface.

Camera and light directions are signed degrees from the flat skin normal (the
direction straight out from the skin), in a single shared plane. Zero points
straight out and positive angles point right. Their average gives the direction
halfway between camera and light: regions whose reflectors face that direction
respond more strongly. A smooth, bell-shaped response allows a spread of platelet
orientations, with a small residual component instead of a sharp on/off boundary.
Each region's strength is normalised to 1 at zero viewing and light angles;
oblique illumination reduces it further using the cosine of the light angle.

Half the difference between the two directions controls a Snell/Bragg-inspired
shift of the reflected wavelength towards blue/violet. An illustrative display
colour ramp converts that wavelength to RGB, while a smooth fade suppresses
reflection as the peak moves beyond the visible range towards ultraviolet.
This approximates angular behaviour; it is not a measured species-specific
spectrum, a full multilayer optical calculation or a polarisation model.

This module returns a colour and relative strength for each region, calculated
once per render. The renderer blends the overlapping regions spatially, bounds
their contributions and applies the overlying pigment filters. Angle changes do
not alter organ geometry, animation timing, perspective or diagnostic-disc colours,
and do not relight the pale backing. Coverage, sharpening and enlargement are
handled separately.
"""

from dataclasses import dataclass
from math import cos, exp, isfinite, pi, radians, sin, sqrt

MAXIMUM_ANGLE_DEGREES = 60.0
ANGLE_PRESETS = (-60.0, -45.0, -30.0, -15.0, 0.0, 15.0, 30.0, 45.0, 60.0)

# Overlapping regions cover the whole skin. Their preferred platelet normals
# vary smoothly across the field, rather than forming three isolated highlights.
# This is an illustrative orientation field, not measured anatomy or skin relief.
REFLECTOR_GRID_SIZE = 7
REFLECTOR_CENTRES = tuple(
    (column / (REFLECTOR_GRID_SIZE - 1), row / (REFLECTOR_GRID_SIZE - 1))
    for row in range(REFLECTOR_GRID_SIZE)
    for column in range(REFLECTOR_GRID_SIZE)
)
PATCH_NORMAL_DEGREES = tuple(
    25 * sin(pi * (x - 0.5)) * cos(0.6 * pi * (y - 0.5)) for x, y in REFLECTOR_CENTRES
)
REFLECTOR_SPREAD_DEGREES = 16.0
DIFFUSE_REFLECTION_FRACTION = 0.08
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
    of the diagnostic discs. Zero/zero defines the reference reflection strength.
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
    """Map a reflected peak wavelength to an illustrative display colour.

    WAVELENGTH_COLOURS contains wavelength/colour anchors ordered from shortest
    to longest wavelength. Between two anchors, each sRGB channel changes linearly
    with wavelength. This gives a continuous colour transition as the camera or
    light angle changes, rather than jumping between a few predefined colours.

    This is a visual approximation, not a conversion of a measured spectrum into
    colour. Wavelengths outside the ramp use its nearest endpoint colour; fading
    reflection towards ultraviolet is handled separately by reflection_responses().

    :param wavelength: Finite reflected peak wavelength in nanometres.
    :return: Three sRGB channels in [0, 255], without premature rounding.
    """
    # Do not extrapolate below the ramp: extending RGB slopes could produce
    # invalid channels and would invent colours outside the illustrative palette.
    if wavelength <= WAVELENGTH_COLOURS[0][0]:
        return WAVELENGTH_COLOURS[0][1]

    # Adjacent anchors define colour segments. Because wavelengths are ordered
    # and the lower endpoint was handled above, the first matching upper bound
    # identifies the segment containing this wavelength.
    for (lower, colour_a), (upper, colour_b) in zip(WAVELENGTH_COLOURS, WAVELENGTH_COLOURS[1:]):
        if wavelength <= upper:
            # A fraction of 0 selects colour_a, 1 selects colour_b, and values
            # between them blend each channel by the same proportion. Keep the
            # fractional channels until the renderer forms its final mixture.
            fraction = (wavelength - lower) / (upper - lower)
            return tuple(a + fraction * (b - a) for a, b in zip(colour_a, colour_b, strict=True))

    # No segment matched, so the wavelength exceeds the longest anchor. Hold
    # that endpoint colour instead of extrapolating beyond the reference palette.
    return WAVELENGTH_COLOURS[-1][1]


def reflection_responses(
    settings: ReflectionSettings = ReflectionSettings(),
) -> tuple[AngularReflection, ...]:
    """Calculate each reflective region's colour and relative strength for a render.

    Two aspects of the angle settings are treated separately. The direction
    halfway between camera and light determines which reflector orientations
    respond most strongly. Half their angular separation determines the shared
    reflected peak wavelength using a Snell/Bragg-inspired approximation.

    Each region has a smooth angular response centred on its preferred normal.
    Dividing by its response at zero camera/light angles gives a relative strength
    of 1 at that reference pose. Strength can exceed 1 when a region becomes
    better aligned; it is a multiplier, not a fraction of total reflected light.
    Oblique lighting and a fade towards ultraviolet attenuate that multiplier.

    The result contains no spatial blending or pigment filtering. The renderer
    applies those later, so these angular calculations need only run once per
    render rather than once for every skin sample. Settings and geometry are
    read without changing simulation state.

    :param settings: Validated signed camera and light angles, in degrees.
    :return: Immutable region responses in PATCH_NORMAL_DEGREES order, with sRGB
        channels in [0, 255] and non-negative relative strength multipliers.
    """
    # With both directions measured outwards from the skin in the same plane,
    # their average is the half-vector direction: the preferred reflector normal
    # for this camera/light pair. Keep it in degrees to compare with region normals.
    half_angle = (settings.view_angle + settings.light_angle) / 2

    # Half the direction difference is the incidence angle relative to that
    # ideal reflector. Its sign does not affect the squared sine below. Convert
    # to radians here because the trigonometric functions require radians.
    incidence = radians((settings.view_angle - settings.light_angle) / 2)

    # Snell's-law-inspired refraction supplies the internal angle factor; the
    # square root approximates the corresponding multilayer peak shift. Greater
    # separation shortens the wavelength. Clamp the radicand to protect sqrt
    # from negative values; the supported angles and current indices keep it positive.
    index_ratio = WATER_REFRACTIVE_INDEX / EFFECTIVE_REFRACTIVE_INDEX
    wavelength = NORMAL_PEAK_WAVELENGTH_NM * sqrt(max(0.0, 1 - (index_ratio * sin(incidence)) ** 2))
    colour = _wavelength_colour(wavelength)

    # The colour ramp clamps at its shortest wavelength rather than becoming
    # invisible. Fade strength separately: zero at/below 360 nm, full at/above
    # 400 nm, with a continuous linear transition between those thresholds.
    visible = max(
        0.0,
        min(
            1.0,
            (wavelength - VISIBLE_FADE_START_NM) / (VISIBLE_FADE_END_NM - VISIBLE_FADE_START_NM),
        ),
    )

    # Oblique light delivers less illumination per unit of flat skin area.
    # Apply this only to the reflective response, not to the pale backing or
    # diagnostic discs. The non-negative clamp excludes negative illumination.
    illumination = max(0.0, cos(radians(settings.light_angle)))
    responses = []
    for normal in PATCH_NORMAL_DEGREES:
        # The Gaussian lobe peaks when the half-vector matches this region's
        # preferred normal. Its width approximates a spread of platelet directions;
        # the residual component prevents an abrupt loss of off-axis reflection.
        lobe = DIFFUSE_REFLECTION_FRACTION + (1 - DIFFUSE_REFLECTION_FRACTION) * exp(
            -0.5 * ((half_angle - normal) / REFLECTOR_SPREAD_DEGREES) ** 2
        )

        # Evaluate the same lobe at the zero-angle pose. Dividing by this value
        # makes every region share the renderer's reference strength, despite
        # their different preferred normals. The residual keeps this divisor positive.
        reference = DIFFUSE_REFLECTION_FRACTION + (1 - DIFFUSE_REFLECTION_FRACTION) * exp(
            -0.5 * (normal / REFLECTOR_SPREAD_DEGREES) ** 2
        )

        # All regions share the peak colour in this planar approximation; their
        # orientations affect strength. The renderer later bounds the mixture
        # with the backing, before overlying pigments attenuate and filter it.
        responses.append(AngularReflection(colour, lobe / reference * illumination * visible))
    return tuple(responses)


DEFAULT_REFLECTION_RESPONSES = reflection_responses()
