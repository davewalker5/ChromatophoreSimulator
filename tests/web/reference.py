"""Emit deterministic reference results from the unmodified Python simulator."""

import json
import os
from random import Random
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from chromatophore_simulator.dynamics import DynamicController, DynamicDisplay
from chromatophore_simulator.model import ChromatophoreField, Pigment, ResponseParameters
from chromatophore_simulator.morphology import generate_layout
from chromatophore_simulator.patterns import Pattern, generate_targets
from chromatophore_simulator.reflection import (
    ANGLE_PRESETS,
    ReflectionSettings,
    reflection_responses,
)
from chromatophore_simulator.timing import generate_response_profiles


def reference_results():
    """Return geometry, signals and state traces for comparison with JavaScript."""
    results = {"patterns": [], "signals": [], "traces": [], "skin": [], "layouts": []}
    results["angular"] = [
        {
            "view": view,
            "light": light,
            "responses": [
                [*response.colour, response.strength]
                for response in reflection_responses(ReflectionSettings(view, light))
            ],
        }
        for view in ANGLE_PRESETS
        for light in ANGLE_PRESETS
    ]
    for rows, columns, seed in [(1, 1, 0), (3, 5, 314159), (7, 1, 2**32 - 1), (50, 50, 314159)]:
        results["layouts"].append(
            {
                "rows": rows,
                "columns": columns,
                "seed": seed,
                "timing": [
                    [*profile.group_id, profile.expansion_scale, profile.contraction_scale]
                    for profile in generate_response_profiles(
                        generate_layout(rows, columns, seed), seed
                    )
                ],
                "geometry": [
                    [organ.x, organ.y, organ.radius_ratio, organ.pigment_index]
                    for organ in generate_layout(rows, columns, seed)
                ],
            }
        )
    for rows, columns in [(1, 1), (5, 7), (50, 50)]:
        for pattern in Pattern:
            if pattern is not Pattern.RANDOM_MOTTLE:
                results["patterns"].append(
                    {
                        "rows": rows,
                        "columns": columns,
                        "pattern": pattern.value,
                        "targets": generate_targets(pattern, rows, columns, Random(1)),
                    }
                )
        for display in DynamicDisplay:
            if display is DynamicDisplay.CHANGING_MOTTLE:
                continue
            controller = DynamicController(display, rows, columns)
            for phase in [0, 0.12, 1.999, 2, 4, 5.5, 8, 15.999, 16, 19.5]:
                results["signals"].append(
                    {
                        "rows": rows,
                        "columns": columns,
                        "display": display.value,
                        "phase": phase,
                        "targets": controller.targets_at(phase),
                    }
                )
    for display in DynamicDisplay:
        if display is DynamicDisplay.CHANGING_MOTTLE:
            continue
        field = ChromatophoreField(5, 7, ResponseParameters(0.5, 0.25, 0.5))
        field.apply_pattern(Pattern.SPOTS, Random(1))
        field.update(0.75)
        field.start_dynamic(display)
        field.set_natural_timing(True)
        for step in range(200):
            if step == 30:
                field.dynamic.speed = 2
            if step == 80:
                field.response = ResponseParameters(2, 0.5, 2)
            if step == 110:
                field.set_pigment_level(Pigment.YELLOW, 0.25)
                field.set_pigment_level(Pigment.BROWN, 0.5)
                field.set_pigment_level(Pigment.BLACK, 0)
            if step == 120:
                field.set_natural_timing(False)
            if step == 150:
                field.set_natural_timing(True)
            if step == 140:
                field.dynamic.speed = 0.5
            field.update([0.01, 0.04, 0.025, 0.1][step % 4])
        results["traces"].append(
            {
                "display": display.value,
                "expansion": [cell.expansion for cell in field.cells],
                "targets": [cell.target_expansion for cell in field.cells],
                "phase": field.dynamic.phase_seconds,
            }
        )
    # Capture the actual Python renderer's sample surface before smooth scaling;
    # interpolation is browser-dependent, but the analytical colours must agree.
    import pygame

    from chromatophore_simulator.view import FieldView

    for rows, columns, view_angle, light_angle in [
        (1, 1, 0, 0),
        (3, 5, 0, 0),
        (50, 50, 0, 0),
        (50, 50, 45, 0),
        (50, 50, -45, 30),
        (3, 5, 60, -60),
    ]:
        for expansion in [0, 0.5, 1]:
            field = ChromatophoreField(rows, columns)
            field.set_expansion(expansion)
            field.update(4)
            renderer = FieldView.__new__(FieldView)
            renderer.surface = pygame.Surface((550, 550))
            renderer.reflection = ReflectionSettings(view_angle, light_angle)
            captured = []
            original_scale = pygame.transform.smoothscale

            def capture_samples(surface, size):
                """Retain sample channels before delegating to the real scaler."""
                for y in range(surface.get_height()):
                    for x in range(surface.get_width()):
                        captured.extend(surface.get_at((x, y)))
                return original_scale(surface, size)

            # Compare optical samples before display sharpening: each viewer may
            # tune edge enhancement independently without changing the skin model.
            with (
                patch("pygame.transform.smoothscale", capture_samples),
                patch("chromatophore_simulator.view.SKIN_SHARPNESS", 0.0),
            ):
                renderer._draw_skin(pygame.Rect(0, 0, 550, 550), field, 550 / max(rows, columns))
            results["skin"].append(
                {
                    "rows": rows,
                    "columns": columns,
                    "expansion": expansion,
                    "view_angle": view_angle,
                    "light_angle": light_angle,
                    "pixels": captured,
                }
            )
    return results


if __name__ == "__main__":
    print(json.dumps(reference_results()))
