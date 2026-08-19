# Future work

Ordered by expected thesis value per unit effort.

1. **Omniscan log parameter fitting** — estimate per-family parameter
   envelopes (looks, ν, stripe σ, dropout λ/μ, roll spectra) automatically
   from real session logs, shipping a "fitted profile" per campaign site.
   Turns defaults into measurements; strengthens the C4 narrative.
2. **Replay validation harness** — drive F3/F4 with logged BlueBoat
   attitude/altitude and score against the recorded waterfall (§validation);
   natural thesis experiment and regression test.
3. **On-the-fly training adapter** — a `torch.utils.data` wrapper applying
   the pipeline at load time (same RNG tree keyed by epoch), avoiding
   dataset materialization for large sweeps.
4. **Bedform synthesis for F7** — directional sand-ripple fields with
   consistent highlight/shadow micro-structure (Jackson & Richardson
   morphologies); the current correlated field is context-only.
5. **GAN/diffusion comparison arm** — style-transfer augmentation baseline
   (per Wei et al. 2024 domain-adaptive line) to compare against
   physics-informed augmentation in the detector ablation — an attractive
   thesis side-experiment.
6. **Equation rendering** — pre-rendered mathtext SVG in science cards and
   encyclopedia (`.[equations]` extra already reserved).
7. **Coherent multipath upgrade** — image-derived reflector map + two-ray
   incoherent summation for wall echoes with correct level falloff.
8. **Per-pixel provenance masks** — export augmentation masks alongside
   images for explainability analyses of detector failures.
