# SAR domain notes for this problem

What was read, what was tested against this stack, and what turned out not to hold here.

## X-band HH over a smallholder kharif system

X-band (9.65 GHz, λ ≈ 3.1 cm) has a shallow penetration depth into a developed canopy. The
standard reading in the literature is that at X-band the return from a closed crop canopy is
dominated by the upper leaf layer, and that as a canopy closes the soil contribution is
progressively attenuated. For a crop whose soil is initially rough or wet — and a
pre-monsoon Gujarat field in June is neither closed nor dry — the net effect on the measured
level can go either way, because two things move at once: soil contribution falls, and
volume scattering from the canopy rises.

The literature therefore does not settle the sign for a specific crop, band, polarisation
and soil condition. **It has to be measured**, and this project measured it before the model
was written rather than assuming it.

### The pre-registration, and its contradiction

`canopy_sign.EXPECTED_SIGN` was written before the optical reference was opened:
attenuation-dominated (greener = darker) for Cotton, Maize, Bajra and Groundnut; the
opposite for Rice, whose transplanted-paddy phase starts with a specular water surface that
a canopy can only brighten.

Measured on 813 plots with ≥90 % clean optical core on both dates, differencing 13 October
against 12 November on **both** instruments so that each plot's own soil brightness and its
own baseline greenness cancel:

| | rho | dB per NDVI unit |
|---|---|---|
| ALL | **+0.569** | +4.93 |
| Rice | +0.551 | +7.84 |
| Cotton | +0.569 | — |
| Maize | +0.647 | — |
| Bajra | +0.334 | — |
| Groundnut | +0.705 | — |

**Four of five predictions were contradicted. At X-band HH over this AOI, a greener plot is
a brighter plot on all five crops.** The finding is reported as a contradiction, and
`EXPECTED_SIGN` was deliberately never edited afterwards.

The most likely reading is that these are small, rough, row-planted fields on soil that
does not stay smooth: the volume term from an erect, structurally rough canopy outruns the
attenuation term across the range of canopy densities actually present here. The two
candidate confounds are handled separately — scene moisture is excluded because T4 and T6
carry near-identical 14-day antecedent rainfall (11.9 against 12.2 mm), and plot-level
irrigation is not excluded and is recorded as an open caveat.

The practical consequence was large. The model had originally been built sign-agnostic on
`|departure|`, which scored **rho = −0.085** against optical — measurably empty. Rebuilt on
the measured signed departure, the season integral scores **+0.564**.

## Two published results this project was calibrated against, read late

Added 2026-09-02. Both were found after the model was fixed, so neither influenced a design
decision — they are stated here as external checks on choices already made, and one of them
partly answers the standing criticism of X-band that §"What was rejected" could only answer
by measurement.

### Inoue, Sakaiya & Wang 2014 — X-band σ⁰ against rice canopy variables

*Potential of X-Band Images from High-Resolution Satellite SAR Sensors to Assess Growth and
Yield in Paddy Rice.* **Remote Sensing 6(7):5995.** doi:10.3390/rs6075995. COSMO-SkyMed and
TerraSAR-X over paddy.

Two findings bear directly on this submission.

**Among all the canopy biophysical variables tested, panicle biomass was the one best
correlated with X-band σ⁰**, and the paper concludes X-band SAR is "promising for direct
assessments of rice grain yields at regional scales" while having "limited capability to
assess the whole-canopy variables". That is the standing X-band criticism stated precisely:
poor for LAI and whole-canopy biomass, and *not* poor for the yield-bearing organ. This
project's target is yield, not LAI. It does not make the saturation objection go away — our
own six-bin NDVI test is what bounds that here — but it means the objection is aimed at a
retrieval this model never attempts.

**The paper's normalisation is the one this project arrived at independently.** Finding a
6.6 dB systematic offset between the two sensors, it proposes an image-based "water-point"
approach: difference each target against a reference surface *within the same image*, because
absolute σ⁰ is not consistent between sensors or images. Our departure-from-own-June-bare-soil
anchor is the same manoeuvre with bare soil as the reference instead of open water. The
convergence is worth stating because the anchor is otherwise the least externally supported
choice in the chain.

**Caveat, and it is not small.** Inoue is VV at shallow incidence over flooded paddy; this
stack is HH at 28.69–35.24° over a mixed rainfed smallholder system. The normalisation
argument transfers cleanly. The panicle result transfers only as far as rice.

### Prashnani & Justice 2026 — SAR phenological metrics over Central Indian smallholdings

*Evaluating SAR-Derived Phenological Metrics for Monsoon (Kharif) Crop Monitoring in
Diversified Agricultural Systems: Insights from Central India.* **Remote Sensing 18(8):1238.**
doi:10.3390/rs18081238. Sentinel-1, 2021 season, five agroclimatic zones, cotton / rice /
maize / soybean / urad — four of our five crops, the same cropping system, the same country.

This is the closest published analogue to the labelling problem here, and it corroborates
three separate choices:

| what it reports | what it corroborates here |
|---|---|
| "cotton showing extended phenology and cereal–legume crops displaying compressed, overlapping growth patterns" | the tier-1 cotton rule is `canopy_end_db ≥ 1.5 dB` on 12 November — the crop still standing when the rest has been cleared. Extended phenology *is* the discriminant. |
| multiclass **48.3 % overall accuracy with systematic cereal–legume confusion, reflecting fundamental phenological convergence among monsoon-aligned crops** | we claim measured labels for **26.5 % of area** and allocate the residual from the district mix, marked as allocated. Against a published ceiling of 48.3 % on the same crop system, that split is calibrated rather than timid. |
| cross-district transferability highest for **rice (74 %) and cotton (72 %)**, the rest lower "due to their phenological similarity" | rice and cotton are **exactly** our two tier-1 crops, and the three we refuse to claim are exactly the three that do not transfer. Independently derived, on different data, in a different state. |
| **AUC25 beat AUC50 and AUC75**, "capturing cumulative backscatter across the broader growing season while remaining robust to soil- and residue-dominated backscatter variability at sowing and harvest" | the model's one per-plot term is a cumulative season integral rather than a peak or a threshold crossing. |
| VH dominated duration and integration metrics; VV dominated intensity metrics | this stack is HH only, so neither is available. Recorded as a limitation of the supplied data, not of the method. |

The last row is the honest counterweight: their integration-based metrics work best in the
polarisation this competition's data does not have.

## Radiometric normalisation across incidence angle

`gamma0 = sigma0 / cos(theta)` is the right first-order normalisation for a rough surface.
It was verified empirically rather than assumed: with incidence spanning 28.69° to 35.24°
across the stack, invariant targets were checked for a residual angle dependence. What
remains after `gamma0` is a scene-level offset, not an angle trend, and it is removed as an
offset (below) rather than as a `cos^n` correction with a fitted exponent.

## Relative radiometric normalisation, and why it is not optional

Persistent-scatterer normalisation over 30 m blocks, selected as the brightest percentile of
the minimum across chosen dates, with a bias-free select/holdout split so the blocks used to
estimate the offset are not the blocks used to measure it.

The result is the single most consequential number in the preprocessing: measured on
16.47 M non-farm AOI pixels, **the district bare-soil level is +1.65 dB higher at T6 than at
T1**. A model that compares November to June without removing that reads a district-wide
radiometric shift as biomass, and — as the back-test showed — a projection rule can score
well by accidentally offsetting it.

## Look direction and row orientation

Row-planted crops backscatter differently depending on the angle between the rows and the
look direction, and that difference **reverses** when the look reverses. T5 is the only
right-looking pass in the stack (azimuth 318.4° against ~135° for the rest), so this is a
real risk rather than a theoretical one.

Row direction is not in the shapefile. It is estimated as the principal axis of a PCA over
each parcel's exterior-ring vertices, and only parcels elongated enough for that axis to
mean something (ratio ≥ 1.5, n = 650) are tested. Both statistics come in clean:

```
rho(angle to the T5 look, t5_anomaly)       = -0.051  (p = 0.195)
rho(cos 2*(row azimuth - look), t5_anomaly) = +0.051  (p = 0.195)
```

T5's level is not used regardless — it is replaced by the T4–T6 interpolation — so only the
residual anomaly was ever at risk.

## The yield link: Monteith

The model's physical frame is Monteith's: biomass accumulates in proportion to intercepted
radiation integrated over the season, and for a given crop and harvest index, yield follows
accumulated biomass. The season canopy integral is the radar analogue of that integral. It
is a proportionality, not a calibration — which is why the integral sets a **within-cohort
modulation** and a published state yield sets the level, rather than the integral being
mapped to t/ha directly.

## What was rejected, and why

- **Sentinel-1 fusion.** A 0.27 ha median plot is about 27 pixels at 10 m, and Round 1
  measured the fusion as negative on this AOI.
- **SoilGrids.** 250 m over a 5.9 × 4.7 km AOI is roughly 24 × 19 pixels. It cannot
  differentiate 0.27 ha plots.
- **A per-plot harvest date.** Attempted and deleted; see `experiments.md`.
- **A double-logistic phenology fit.** Three canopy samples cannot constrain four
  parameters. The season integral is a trapezoid over what was actually observed.
