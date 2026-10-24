"""Draw individual pigment discs without changing simulation state.

This diagnostic renderer uses each organ's fixed position, pigment and maximum
radius with its current expansion. Palette and minimum visible radius live here
so Skin View can use the same pigment colours and contracted-disc coverage.
Window layout, controls and mode selection remain in view.py.
"""

from types import MappingProxyType

import pygame

from chromatophore_simulator.model import ChromatophoreField, Pigment

# Illustrative common cuttlefish palette; black represents dark brown.
PIGMENT_COLOURS = MappingProxyType(
    {
        Pigment.YELLOW: (190, 145, 52),
        Pigment.RED: (155, 74, 46),
        Pigment.BROWN: (85, 56, 40),
        Pigment.BLACK: (43, 34, 29),
    }
)

MINIMUM_RADIUS = 0.8


def draw_chromatophores(
    surface: pygame.Surface,
    field: ChromatophoreField,
    left: float,
    top: float,
    spacing: float,
) -> None:
    """Draw fixed organ geometry at its current animated expansion.

    :param surface: Destination surface; background is prepared by the view.
    :param field: Read-only field, including organ geometry and pigment identity.
    :param left: Grid's left edge in destination pixels.
    :param top: Grid's top edge in destination pixels.
    :param spacing: Destination pixels per logical cell spacing.
    """
    # Contracted organs keep a diagnostic dot, capped by their fixed maximum radius.
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
        pygame.draw.aacircle(surface, PIGMENT_COLOURS[cell.pigment], centre, radius)
