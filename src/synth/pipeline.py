"""Generate one Drift-Sense sample: a reference/search pair with exact ground truth.

Physical setup
--------------
A single device layout is rendered once at 1 nm/px, then **imaged twice** under different
conditions:

* the **reference** is a 1000x1000 crop at 1 nm/px - a careful, high-dose 100x acquisition;
* the **search** is a 1000x1000 view of a wider field at ``scale`` nm/px - a fast, low-dose 10x
  acquisition covering ~10x the linear area.

Both come from the *same* underlying geometry but are separate captures with independent noise, so
the 10:1 magnification relationship falls out of the pixel-size ratio rather than being imposed by
resizing one image into the other.

Two things this does that the sponsor's generator cannot
--------------------------------------------------------
**Continuous ground truth.** The crop origin is *fractional*, and the crop is taken with a sub-pixel
warp. The sponsor's generator uses integer origins in the fine canvas, which quantises ground truth
to a 0.1 px grid in search coordinates - so no sub-pixel claim below that can be demonstrated on
their data. Ground truth here is exact and continuous, computed analytically from the same transform
used to render.

**Rotation and scale.** The problem statement says 9:1-11:1 magnification and 1-2 degrees of
rotation will be tested. The sponsor's generator produces neither (verified as H9). This one does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from src.synth import imaging, layout, optical

REFERENCE_SIZE_PX = 1000
SEARCH_SIZE_PX = 1000
PIXEL_SIZE_REF_NM = 1.0


@dataclass
class GenerationParams:
    """Sampling ranges for one dataset. Each pair draws its own values from these."""

    # --- magnification and pose. The sponsor's generator has neither. ---
    scale_min: float = 9.0
    scale_max: float = 11.0
    rotation_deg_max: float = 2.0

    # --- structure ---
    architectures: tuple[str, ...] = ("dram",)
    mat_size_nm: float = 2600.0
    strip_width_nm: float = 320.0
    boundary_bias: float = 0.35
    linewidth_bias_nm: float = 0.0
    corner_rounding_px: float = 0.0

    # --- SE response (omitted entirely by the sponsor's generator) ---
    edge_gain_min: float = 0.35
    edge_gain_max: float = 0.75
    edge_sigma_nm: float = 2.0
    charging_strength: float = 0.10

    # --- optics ---
    beam_spot_size_nm: float = 5.0
    astigmatism_ratio: float = 1.0

    # --- modality. "sem" is the graded task; "optical" is the spec's RGB bonus. ---
    #
    # The optical path is NOT the SEM path in colour. An optical microscope is diffraction-limited
    # at 0.61*lambda/NA = 373 nm, six times the DRAM word-line pitch, so the cell lattice is not
    # blurred - it is gone. Identity has to come from the mat/strip structure instead, which is why
    # the optical modality images at a coarser plate scale. See src/synth/optical.py.
    modality: str = "sem"
    optical_numerical_aperture: float = 0.90
    optical_chromatic_aberration: float = 0.0010
    optical_dose: float = 900.0
    optical_read_sigma: float = 2.5

    # --- dose: the search image is a faster, noisier acquisition ---
    dose_reference: float = 2000.0
    dose_search: float = 200.0
    detector_noise_sigma_ref: float = 2.0
    detector_noise_sigma_search: float = 5.0

    # --- scan artefacts, search image only unless noted ---
    shear_amplitude_px: float = 1.5
    drift_jitter_px: float = 0.5
    barrel_distortion_k: float = 0.0
    vignette_strength: float = 0.0
    gamma: float = 1.0
    speckle_sigma: float = 0.0
    salt_pepper_prob: float = 0.0
    charging_streak_prob: float = 0.0
    charging_streak_intensity: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Sample:
    reference: np.ndarray
    search: np.ndarray
    gt_x: float
    gt_y: float
    metadata: dict = field(default_factory=dict)


def _pick_preset(architecture: str, rng: np.random.Generator):
    pool = layout.DRAM_PRESETS if architecture == "dram" else layout.FINFET_PRESETS
    return pool[list(pool)[int(rng.integers(0, len(pool)))]]


def _crop_reference(canvas: np.ndarray, x0_nm: float, y0_nm: float) -> np.ndarray:
    """Cut the reference field of view at a FRACTIONAL origin.

    Uses the same rotation/scale machinery at 1 nm/px and zero rotation, so the sub-pixel offset is
    applied by the identical code path that renders the search image - which keeps ground truth
    exactly consistent between the two.
    """
    centre = (x0_nm + REFERENCE_SIZE_PX / 2.0, y0_nm + REFERENCE_SIZE_PX / 2.0)
    return imaging.resample_field_of_view(
        canvas, REFERENCE_SIZE_PX, PIXEL_SIZE_REF_NM, 0.0, centre
    )


def _per_channel(rgb: np.ndarray, fn) -> np.ndarray:
    """Apply a single-channel geometric operation to each channel of an HxWx3 image.

    The crop and field-of-view resample are pure geometry, so running them per channel is exactly
    equivalent to a 3-channel version and avoids duplicating either one. Chromatic aberration is
    applied earlier, in the optical renderer, where it belongs.
    """
    planes = [fn(rgb[..., c]) for c in range(rgb.shape[2])]
    return np.stack(planes, axis=-1)


def _generate_optical(seed: int, params: GenerationParams, struct_rng, ref_rng, search_rng,
                      built, canvas_px, scale, rotation, architecture, preset,
                      cx, cy, x0_nm, y0_nm, search_centre) -> tuple:
    """The RGB optical acquisition, sharing the SEM path's geometry exactly.

    Sharing the geometry is deliberate: ground truth, the crop origin and the field-of-view
    transform are identical, so any difference in the measured result is caused by the imaging
    physics and by nothing else. What changes is everything after the layout:

      SEM       SE yield -> charging -> beam PSF -> sample -> Poisson -> Gaussian
      optical   film-stack reflectance per channel -> chromatic aberration -> diffraction
                -> illumination -> sample -> Poisson and Gaussian per channel

    WHAT THE PLATE SCALE MEANS. One canvas unit is ``PIXEL_SIZE_OPTICAL_NM`` here rather than 1 nm,
    so the same rendered layout stands for a **coarser layer** - metal routing and mat boundaries
    rather than the cell array. That is not a convenience: an optical microscope resolves
    0.61*lambda/NA = 373 nm, and a 64 nm cell pitch is simply not there to be imaged. Optical
    inspection is used on coarse layers for exactly this reason, so imaging one is the honest
    translation of the task rather than a colourised SEM.
    """
    optical_params = optical.OpticalParams(
        pixel_size_nm=optical.PIXEL_SIZE_OPTICAL_NM,
        numerical_aperture=params.optical_numerical_aperture,
        chromatic_aberration=params.optical_chromatic_aberration,
    )
    # Diffraction is a property of the objective, so it is applied ONCE to the shared scene at
    # canvas resolution - the same argument that puts the beam PSF before the split in the SEM path.
    scene_rgb = optical.render_optical(built.canvas, optical_params)

    reference = optical.optical_detector(
        _per_channel(scene_rgb, lambda plane: _crop_reference(plane, x0_nm, y0_nm)),
        params.optical_dose, params.optical_read_sigma, ref_rng,
    )
    sampled = _per_channel(
        scene_rgb,
        lambda plane: imaging.resample_field_of_view(
            plane, SEARCH_SIZE_PX, scale, rotation, search_centre
        ),
    )
    # The search acquisition is faster and therefore noisier, exactly as in the SEM path.
    search = optical.optical_detector(
        sampled, params.optical_dose / 8.0, params.optical_read_sigma * 2.0, search_rng,
    )
    _ = (struct_rng, canvas_px, architecture, preset, cx, cy, seed)
    return reference, search


def generate_sample(seed: int, params: GenerationParams) -> Sample:
    """Generate one reference/search pair with exact, continuous ground truth."""
    # Separate streams: structure, reference acquisition, search acquisition. The two acquisitions
    # must be independent - see imaging.detector_chain.
    struct_rng = np.random.default_rng(seed)
    ref_rng = np.random.default_rng(seed * 7919 + 1)
    search_rng = np.random.default_rng(seed * 1_000_003 + 7)

    architecture = params.architectures[int(struct_rng.integers(0, len(params.architectures)))]
    preset = _pick_preset(architecture, struct_rng)

    scale = float(struct_rng.uniform(params.scale_min, params.scale_max))
    rotation = float(struct_rng.uniform(-params.rotation_deg_max, params.rotation_deg_max))

    # The canvas must cover the search field of view: 1000 px at `scale` nm/px.
    canvas_px = int(round(SEARCH_SIZE_PX * scale))

    built = layout.build_canvas(
        canvas_px, architecture, preset, struct_rng,
        mat_size_nm=params.mat_size_nm, strip_width_nm=params.strip_width_nm,
        linewidth_bias_nm=params.linewidth_bias_nm,
        corner_rounding_px=params.corner_rounding_px,
    )

    # The optical modality replaces every imaging stage below but shares all the geometry above and
    # below it, so the two modalities differ by physics alone. Its own chain lives in
    # _generate_optical; the SEM chain continues here.
    optical_mode = params.modality == "optical"

    # Steps 2-3: SE response and charging. Applied ONCE to the shared scene, because they are
    # properties of the sample and the beam-sample interaction, not of a particular acquisition.
    edge_gain = float(struct_rng.uniform(params.edge_gain_min, params.edge_gain_max))
    scene = imaging.secondary_electron_response(
        built.canvas, edge_gain=edge_gain, edge_sigma_nm=params.edge_sigma_nm,
        pixel_size_nm=PIXEL_SIZE_REF_NM, rng=struct_rng,
    )
    scene = scene * imaging.charging_field(scene.shape, params.charging_strength, struct_rng)
    scene = np.clip(scene, 0, 255).astype(np.float32)

    # Step 4: the beam PSF is a property of the instrument, so it applies to both acquisitions
    # identically, before either is sampled.
    scene = imaging.beam_psf(scene, params.beam_spot_size_nm, PIXEL_SIZE_REF_NM,
                             params.astigmatism_ratio)

    # Choose where the reference was taken. Fractional origin -> continuous ground truth.
    margin = REFERENCE_SIZE_PX / 2.0 + 4.0
    strips = built.strip_rects
    if strips and struct_rng.random() < params.boundary_bias:
        # Deliberately place some crops across a mat/strip boundary: those carry an aperiodic
        # landmark and are the easy cases. The rest sit deep inside a mat and are the hard ones.
        sx, sy, sw, sh = strips[int(struct_rng.integers(0, len(strips)))]
        cx = sx + sw / 2.0 + float(struct_rng.uniform(-250, 250))
        cy = sy + sh / 2.0 + float(struct_rng.uniform(-250, 250))
    else:
        cx = float(struct_rng.uniform(margin, canvas_px - margin))
        cy = float(struct_rng.uniform(margin, canvas_px - margin))
    cx = float(np.clip(cx, margin, canvas_px - margin))
    cy = float(np.clip(cy, margin, canvas_px - margin))

    x0_nm, y0_nm = cx - REFERENCE_SIZE_PX / 2.0, cy - REFERENCE_SIZE_PX / 2.0

    # Reference acquisition: high dose, no shear (a careful, slow scan).
    ref_params = imaging.AcquisitionParams(
        pixel_size_nm=PIXEL_SIZE_REF_NM,
        beam_spot_size_nm=params.beam_spot_size_nm,
        dose=params.dose_reference,
        detector_noise_sigma=params.detector_noise_sigma_ref,
        astigmatism_ratio=params.astigmatism_ratio,
        shear_amplitude_px=0.0,
        drift_jitter_px=params.drift_jitter_px * 0.2,
        barrel_distortion_k=params.barrel_distortion_k * 0.3,
        gamma=params.gamma,
    )
    reference = imaging.detector_chain(_crop_reference(scene, x0_nm, y0_nm), ref_params, ref_rng)

    # Search acquisition: wide field, low dose, full scan artefacts.
    search_centre = (canvas_px / 2.0, canvas_px / 2.0)
    sampled = imaging.resample_field_of_view(
        scene, SEARCH_SIZE_PX, scale, rotation, search_centre
    )
    search_params = imaging.AcquisitionParams(
        pixel_size_nm=scale,
        beam_spot_size_nm=params.beam_spot_size_nm,
        dose=params.dose_search,
        detector_noise_sigma=params.detector_noise_sigma_search,
        astigmatism_ratio=params.astigmatism_ratio,
        shear_amplitude_px=params.shear_amplitude_px,
        drift_jitter_px=params.drift_jitter_px,
        barrel_distortion_k=params.barrel_distortion_k,
        vignette_strength=params.vignette_strength,
        gamma=params.gamma,
        speckle_sigma=params.speckle_sigma,
        salt_pepper_prob=params.salt_pepper_prob,
        charging_streak_prob=params.charging_streak_prob,
        charging_streak_intensity=params.charging_streak_intensity,
    )
    search = imaging.detector_chain(sampled, search_params, search_rng)

    if optical_mode:
        reference, search = _generate_optical(
            seed, params, struct_rng, ref_rng, search_rng, built, canvas_px, scale, rotation,
            architecture, preset, cx, cy, x0_nm, y0_nm, search_centre,
        )

    # Ground truth: computed analytically from the SAME transform used to render, never measured
    # back off the image. Exact and continuous.
    gt_x, gt_y = imaging.canvas_to_search_coords(
        cx, cy, SEARCH_SIZE_PX, scale, rotation, search_centre
    )
    # ...and then through every geometric stage that runs AFTER the sampling, or the label describes
    # a different image than the one we saved. Barrel distortion is applied inside detector_chain,
    # so a ground truth stopping here sits in the pre-distortion frame while the content has moved.
    # Caught by the robustness sweep: at k=0.05 the localizer's residual pointed radially inward on
    # 97% of pairs and grew as r^2, which is the distortion's own signature, not a matching error.
    # See ADR-0028 and FINDINGS section 25.
    if params.barrel_distortion_k:
        gt_x, gt_y = imaging.barrel_map_point(
            gt_x, gt_y, (SEARCH_SIZE_PX, SEARCH_SIZE_PX), params.barrel_distortion_k
        )

    box = REFERENCE_SIZE_PX / scale
    ambiguity = _ambiguity_level(built, cx, cy)

    return Sample(
        reference=reference, search=search, gt_x=gt_x, gt_y=gt_y,
        metadata={
            "architecture": architecture,
            "modality": params.modality,
            "preset": getattr(preset, "name", architecture),
            "scale_ratio": scale,
            "rotation_deg": rotation,
            "gt_box_x": gt_x - box / 2.0, "gt_box_y": gt_y - box / 2.0,
            "gt_box_w": box, "gt_box_h": box,
            "crop_centre_x_nm": cx, "crop_centre_y_nm": cy,
            "canvas_px": canvas_px,
            "edge_brightness_A": edge_gain,
            "edge_sigma_nm": params.edge_sigma_nm,
            "beam_spot_size_nm": params.beam_spot_size_nm,
            "dose_reference": params.dose_reference,
            "dose_search": params.dose_search,
            "detector_noise_sigma_ref": params.detector_noise_sigma_ref,
            "detector_noise_sigma_search": params.detector_noise_sigma_search,
            "shear_amplitude_px": params.shear_amplitude_px,
            "drift_jitter_px": params.drift_jitter_px,
            "astigmatism_ratio": params.astigmatism_ratio,
            "vignette_strength": params.vignette_strength,
            "gamma": params.gamma,
            "barrel_distortion_k": params.barrel_distortion_k,
            "charging_streak_prob": params.charging_streak_prob,
            "charging_streak_intensity": params.charging_streak_intensity,
            "speckle_sigma": params.speckle_sigma,
            "salt_pepper_prob": params.salt_pepper_prob,
            "linewidth_bias_nm": params.linewidth_bias_nm,
            "corner_rounding_px": params.corner_rounding_px,
            "mat_size_nm": params.mat_size_nm,
            "strip_width_nm": params.strip_width_nm,
            "boundary_bias": params.boundary_bias,
            "ambiguity_level": ambiguity,
            "seed": seed,
        },
    )


def _ambiguity_level(built: layout.LayoutResult, cx: float, cy: float) -> str:
    """How hard is this pair? Based on whether an aperiodic landmark is in view.

    A crop containing a mat/strip boundary has a unique landmark and is easy. One deep inside a mat
    sees only the repeating lattice and is genuinely ambiguous. Stratifying results by this shows
    where a method actually fails rather than averaging the two regimes together.
    """
    half = REFERENCE_SIZE_PX / 2.0
    for sx, sy, sw, sh in built.strip_rects:
        if (cx + half > sx and cx - half < sx + sw) and (cy + half > sy and cy - half < sy + sh):
            return "low"
    nearest = min(
        (min(abs(cx - sx), abs(cx - (sx + sw)), abs(cy - sy), abs(cy - (sy + sh)))
         for sx, sy, sw, sh in built.strip_rects), default=1e9,
    )
    return "med" if nearest < 2.5 * REFERENCE_SIZE_PX else "high"
