# F5 — Ping loss & sensor artifacts

## 1. Physical explanation
Real acquisition chains lose or corrupt whole pings: WiFi/telemetry link
congestion on a USV, logger back-pressure at high ping rates, power dips.
Lost pings appear as black rows (zero-fill), repeated rows (sample-and-hold
in the logging software), or are silently *removed*, compressing the
waterfall along track. Per-ping receiver gain jitter produces horizontal
striping with short-term correlation (an AR(1)-like dB process); acoustic
interference from other active sources produces bright streaks confined to
part of the range extent.

## 2. Mathematical model
```
Dropout bursts:  events ~ Poisson(λ per 100 rows), burst length ~ Geometric(1/μ)
  mode black:   I'(y, ·) = 0                     for y ∈ burst
  mode hold:    I'(y, ·) = I(y_prev, ·)           for y ∈ burst
  mode remove:  rows deleted -> along-track compression (labels re-mapped)
Striping:  I'(y, r) = I(y, r) · 10^(g(y)/10),  g(y+1) = ρ·g(y) + ε(y),
           stationary std = stripe_sigma_db (ρ from correlation length)
Interference: bright speckled segment of random range extent in random rows.
```

## 3. Implementation
Burst sampling from the deterministic RNG; `remove` mode builds a
row-keep index and the corresponding bidirectional row warp so YOLO boxes
translate/compress exactly with the pixels (boxes fully inside removed spans
are dropped and logged in provenance). The stripe process is exact AR(1) in
dB applied multiplicatively in the linear domain.

## 4. References
- Blondel, P. (2009). *The Handbook of Sidescan Sonar*, Springer, ch. 5
  (data acquisition artifacts).
- Abraham, D.A. (2019). *Underwater Acoustic Signal Processing*, Springer
  (receiver noise and gain processes).

## 5. Expected visual effect
Isolated or clustered black/repeated rows; subtle horizontal banding; short
bright streaks; in `remove` mode a slightly shortened image with locally
compressed features.

## 6. Limitations
Independent of platform state (real link loss correlates with distance from
the base station and maneuvering); interference is phenomenological, not a
model of a specific interferer.

## 7. Validation
Count dropout events and burst-length histogram in real session logs
(Omniscan ping counters expose gaps); match λ and μ. Striping: estimate
row-mean dB autocorrelation on real vs augmented backgrounds.
