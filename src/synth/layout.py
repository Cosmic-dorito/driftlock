"""Device layout rendering: DRAM 6F^2 arrays and FinFET, drawn at 1 nm per pixel.

Everything here is public structural knowledge - the geometric *relationships* that define these
architectures (2F/3F pitch ratios in a folded-bitline DRAM cell, fin/gate pitch scaling in FinFET).
No proprietary fab data is used, as the problem statement requires.

Two properties matter for the localization problem and are modelled deliberately:

**Imperfect periodicity.** Line positions are laid down as a random walk
(``pos += pitch + N(0, jitter)``) rather than on an exact grid, and every drawn element gets its own
width perturbation. This is a real effect - line-edge roughness and CD variation - and it is also
the *only* thing that makes one cell distinguishable from its neighbours. A perfectly periodic array
would be impossible to localize within, by anyone.

**Zone structure.** Arrays are broken into mats separated by peripheral routing strips, so the
canvas contains aperiodic landmarks at a coarser scale than the cell pitch. Each mat is generated
independently, so crossing a mat boundary genuinely changes the pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# Grey levels for the flattened top-down view. An SEM sees the exposed surface, not a colour-coded
# stack, so these are material contrast levels rather than layer identifiers.
BACKGROUND = 40
WORD_LINE = 150
BIT_LINE = 170
CONTACT = 225
FIN = 160
GATE = 195
SD_CONTACT = 230
ROUTING = 120


@dataclass
class DramPreset:
    """DRAM 6F^2 folded-bitline geometry, in nanometres."""

    word_line_pitch_nm: float = 64.0
    word_line_width_nm: float = 32.0
    bit_line_pitch_nm: float = 96.0
    bit_line_width_nm: float = 32.0
    contact_diameter_nm: float = 32.0
    position_jitter_nm: float = 1.5
    width_jitter_frac: float = 0.10
    name: str = "dram_1x"


@dataclass
class FinfetPreset:
    """FinFET fin/gate/contact geometry, in nanometres."""

    fin_pitch_nm: float = 48.0
    fin_width_nm: float = 16.0
    gate_pitch_nm: float = 90.0
    gate_length_nm: float = 28.0
    contact_size_nm: float = 28.0
    position_jitter_nm: float = 1.2
    width_jitter_frac: float = 0.10
    name: str = "finfet_10nm"


DRAM_PRESETS = {
    "dram_1x": DramPreset(),
    "dram_dense": DramPreset(48, 24, 72, 24, 24, name="dram_dense"),
    "dram_loose": DramPreset(96, 48, 144, 48, 48, name="dram_loose"),
    "dram_legacy": DramPreset(160, 78, 240, 80, 78, name="dram_legacy"),
}

FINFET_PRESETS = {
    "finfet_10nm": FinfetPreset(),
    "finfet_7nm": FinfetPreset(40, 14, 76, 24, 24, name="finfet_7nm"),
    "finfet_14nm": FinfetPreset(60, 20, 110, 34, 34, name="finfet_14nm"),
    "finfet_28nm": FinfetPreset(96, 32, 180, 56, 52, name="finfet_28nm"),
}

ALL_PRESETS: dict[str, DramPreset | FinfetPreset] = {**DRAM_PRESETS, **FINFET_PRESETS}


@dataclass
class LayoutResult:
    canvas: np.ndarray
    mat_rects: list[tuple[int, int, int, int]] = field(default_factory=list)
    strip_rects: list[tuple[int, int, int, int]] = field(default_factory=list)
    preset_name: str = ""


def _line_positions(extent_px: int, pitch_nm: float, jitter_nm: float,
                    rng: np.random.Generator) -> np.ndarray:
    """Line centres as a random walk rather than an exact grid.

    The accumulating deviation is what gives each cell a unique fingerprint. Over a 1000 nm
    reference crop with 1.5 nm steps the walk drifts by roughly 6 nm, which after 10x
    downsampling is a ~0.6 px geometric signature in the search image - faint, but the only
    signal that distinguishes one lattice repeat from another.
    """
    positions = []
    pos = float(rng.uniform(0, pitch_nm))
    while pos < extent_px:
        positions.append(pos)
        pos += pitch_nm + rng.normal(0, jitter_nm)
    return np.asarray(positions, dtype=np.float64)


def _stripe_mask(extent_px: int, positions: np.ndarray, width_nm: float,
                 width_jitter_frac: float, rng: np.random.Generator,
                 linewidth_bias_nm: float = 0.0) -> np.ndarray:
    """1D boolean mask of drawn lines, each with its own width perturbation.

    ``linewidth_bias_nm`` is a deterministic global CD bias - the "polygon scaling" knob that
    models systematic over- or under-exposure and etch bias, on top of per-instance jitter.
    """
    mask = np.zeros(extent_px, dtype=bool)
    if positions.size == 0:
        return mask
    nominal = max(width_nm + linewidth_bias_nm, 1.0)
    widths = nominal * (1.0 + rng.normal(0, width_jitter_frac, size=positions.size))
    widths = np.clip(widths, nominal * 0.5, nominal * 1.5)
    for centre, width in zip(positions, widths):
        lo = int(round(centre - width / 2.0))
        hi = int(round(centre + width / 2.0))
        mask[max(lo, 0):min(hi, extent_px)] = True
    return mask


def render_dram(size_px: int, preset: DramPreset, rng: np.random.Generator,
                linewidth_bias_nm: float = 0.0) -> np.ndarray:
    """Render a DRAM 6F^2 folded-bitline array: word lines, bit lines, storage-node contacts.

    Contacts sit on an ``(i + j) % 2`` checkerboard - one per two cells, as in a real folded-bitline
    layout rather than a naive full grid. That parity has a direct consequence for localization:
    shifting by one pitch along a single axis breaks the checkerboard and is detectable, whereas the
    diagonal shift (one word line AND one bit line) preserves it and is the genuinely dangerous
    confusion.
    """
    canvas = np.full((size_px, size_px), BACKGROUND, dtype=np.uint8)

    word_pos = _line_positions(size_px, preset.word_line_pitch_nm, preset.position_jitter_nm, rng)
    bit_pos = _line_positions(size_px, preset.bit_line_pitch_nm, preset.position_jitter_nm, rng)

    rows = _stripe_mask(size_px, word_pos, preset.word_line_width_nm,
                        preset.width_jitter_frac, rng, linewidth_bias_nm)
    cols = _stripe_mask(size_px, bit_pos, preset.bit_line_width_nm,
                        preset.width_jitter_frac, rng, linewidth_bias_nm)

    canvas[rows, :] = np.maximum(canvas[rows, :], WORD_LINE)
    canvas[:, cols] = np.maximum(canvas[:, cols], BIT_LINE)

    radius_nm = max(preset.contact_diameter_nm + linewidth_bias_nm, 1.0) / 2.0
    for i, wl in enumerate(word_pos):
        for j, bl in enumerate(bit_pos):
            if (i + j) % 2:
                continue
            r = max(1, int(round(radius_nm * (1.0 + rng.normal(0, preset.width_jitter_frac)))))
            cv2.circle(canvas, (int(round(bl)), int(round(wl))), r, CONTACT, -1)
    return canvas


def render_finfet(size_px: int, preset: FinfetPreset, rng: np.random.Generator,
                  linewidth_bias_nm: float = 0.0) -> np.ndarray:
    """Render a FinFET top-down view: vertical fins, horizontal gates, source/drain contacts.

    Less ambiguous than DRAM by construction - the gate lines break periodicity along one axis -
    which is exactly why it is the secondary architecture. Solving the harder case implies this one.
    """
    canvas = np.full((size_px, size_px), BACKGROUND, dtype=np.uint8)

    fin_pos = _line_positions(size_px, preset.fin_pitch_nm, preset.position_jitter_nm, rng)
    gate_pos = _line_positions(size_px, preset.gate_pitch_nm, preset.position_jitter_nm, rng)

    fins = _stripe_mask(size_px, fin_pos, preset.fin_width_nm,
                        preset.width_jitter_frac, rng, linewidth_bias_nm)
    gates = _stripe_mask(size_px, gate_pos, preset.gate_length_nm,
                         preset.width_jitter_frac, rng, linewidth_bias_nm)

    canvas[:, fins] = np.maximum(canvas[:, fins], FIN)
    canvas[gates, :] = np.maximum(canvas[gates, :], GATE)

    # Source/drain contacts land on fins, between gates.
    half = max(preset.contact_size_nm + linewidth_bias_nm, 1.0) / 2.0
    for gi in range(len(gate_pos) - 1):
        mid_y = int(round(0.5 * (gate_pos[gi] + gate_pos[gi + 1])))
        if not (0 <= mid_y < size_px):
            continue
        for fx in fin_pos:
            x = int(round(fx))
            s = int(round(half * (1.0 + rng.normal(0, preset.width_jitter_frac))))
            if s < 1:
                continue
            cv2.rectangle(canvas, (x - s, mid_y - s), (x + s, mid_y + s), SD_CONTACT, -1)
    return canvas


def _routing_texture(height: int, width: int, rng: np.random.Generator) -> np.ndarray:
    """Peripheral/routing material: mid-grey fill with sparse orthogonal interconnect."""
    tile = np.full((height, width), ROUTING, dtype=np.uint8)
    for _ in range(max(1, int(width / 260))):
        x = int(rng.integers(0, max(width - 1, 1)))
        w = int(rng.integers(6, 22))
        tile[:, x:x + w] = np.maximum(tile[:, x:x + w], ROUTING + 55)
    for _ in range(max(1, int(height / 260))):
        y = int(rng.integers(0, max(height - 1, 1)))
        h = int(rng.integers(6, 22))
        tile[y:y + h, :] = np.maximum(tile[y:y + h, :], ROUTING + 40)
    return tile


def _zone_spans(total_px: int, mat_px: int, strip_px: int) -> tuple[list, list]:
    """Alternating mat / strip spans covering one axis."""
    mats, strips, pos = [], [], 0
    while pos < total_px:
        end = min(pos + mat_px, total_px)
        mats.append((pos, end))
        pos = end
        if pos >= total_px:
            break
        end = min(pos + strip_px, total_px)
        strips.append((pos, end))
        pos = end
    return mats, strips


def build_canvas(size_px: int, architecture: str, preset, rng: np.random.Generator,
                 mat_size_nm: float = 2600.0, strip_width_nm: float = 320.0,
                 linewidth_bias_nm: float = 0.0, corner_rounding_px: float = 0.0,
                 vary_preset_per_mat: bool = False) -> LayoutResult:
    """Compose the full fine canvas: independently generated mats separated by routing strips.

    Each mat is rendered with its **own** RNG draw, so line positions differ across mats. That is
    what makes a mat boundary a genuine landmark rather than a cosmetic feature, and it is why a
    reference crop that includes one is far easier to localize.

    ``vary_preset_per_mat`` additionally perturbs the nominal PITCH between mats. It defaults to
    **off**, and that default was changed on 12 Aug (another machine) after it turned out to be both
    physically wrong and measurably harmful:

    * **Wrong.** A cell array's pitch is a design rule fixed by lithography; every mat on a die is
      the same layout stepped and repeated. Mats differ in line-edge roughness and local CD, which
      we already model per instance - they do not differ in pitch by 6%. A process engineer would
      spot this immediately.
    * **Harmful, and it hid behind a plausible motive.** It was added for "diversity", but it
      destroys the one quantity that makes magnification measurable: with each mat on its own
      pitch, the search image has no single pitch to compare against the reference's. Measured, it
      pushed the lattice-based scale estimate from 0.69% error to **4.1%** - far outside the ~1%
      basin correlation can recover from.

    Diversity across the dataset comes from drawing a different preset per SAMPLE, which is where
    it belongs. Kept as a flag so the effect stays reproducible as an ablation row.
    """
    canvas = np.zeros((size_px, size_px), dtype=np.uint8)
    mat_px = max(int(round(mat_size_nm)), 64)
    strip_px = max(int(round(strip_width_nm)), 8)

    x_mats, x_strips = _zone_spans(size_px, mat_px, strip_px)
    y_mats, y_strips = _zone_spans(size_px, mat_px, strip_px)

    render = render_dram if architecture == "dram" else render_finfet

    mat_rects, strip_rects = [], []
    for (y0, y1) in y_mats:
        for (x0, x1) in x_mats:
            h, w = y1 - y0, x1 - x0
            local = preset
            if vary_preset_per_mat:
                scale = float(rng.uniform(0.94, 1.06))
                local = type(preset)(**{
                    k: (v * scale if isinstance(v, float) and k.endswith("_nm")
                        and "jitter" not in k else v)
                    for k, v in vars(preset).items()
                })
            tile = render(max(h, w), local, rng, linewidth_bias_nm)
            canvas[y0:y1, x0:x1] = tile[:h, :w]
            mat_rects.append((x0, y0, w, h))

    for (y0, y1) in y_strips:
        canvas[y0:y1, :] = _routing_texture(y1 - y0, size_px, rng)
        strip_rects.append((0, y0, size_px, y1 - y0))
    for (x0, x1) in x_strips:
        canvas[:, x0:x1] = _routing_texture(size_px, x1 - x0, rng)
        strip_rects.append((x0, 0, x1 - x0, size_px))

    if corner_rounding_px >= 0.5:
        k = max(1, int(round(corner_rounding_px)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        canvas = cv2.morphologyEx(canvas, cv2.MORPH_OPEN, kernel)
        canvas = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE, kernel)

    return LayoutResult(canvas, mat_rects, strip_rects, getattr(preset, "name", architecture))
