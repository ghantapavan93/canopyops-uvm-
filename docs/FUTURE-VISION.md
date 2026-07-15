# CanopyOps — Future Vision (2026 → 2031)

> **The next five years of vegetation *assurance*.**
> Where today's closed-loop record grows into a sensing-to-outcome system — with
> AI that finds the risk and humans who make every call.

*Independent concept. All data is synthetic. Not affiliated with, or endorsed by,
The Davey Tree Expert Company. This is a forward-looking design document, grounded
in public industry sources (cited inline); nothing here claims to be implemented
beyond the current prototype.*

---

## 0. Where we are today

CanopyOps already proves the thesis **"closed ≠ effective"** end to end: a plan
with a measurable outcome → offline field execution → evidence-completeness gate →
environmental-constraint checks → follow-up verification → a human-approved,
audit-linked **Proof Pack**. On the platform side it adds live geofencing
(offline-capable), 3D terrain/slope awareness, an SAP-style **OData** integration
seam (WBS/CATS), real basemaps, an installable offline-first **PWA**, and
Prometheus-scrapeable observability.

That maps cleanly onto how the industry's leading UVM data spine is organized —
field dispatch, offline-tolerant mobile capture, and a compliance/reliability
dashboard (the shape of Davey's **ResourceKeeper** Rover / Mobile / Insight
modules). The vision below extends the *outcome* spine forward into *sensing* and
*prediction*, without ever handing a safety or compliance decision to a machine.

---

## 1. The thesis for the next five years

Today a crew finds risk by driving the line and a planner prioritizes by cycle.
The next five years invert that: **remote sensing finds the risk continuously, AI
ranks it, and human experts spend their judgment on decisions instead of on
discovery.** Every layer we add must (a) shorten the distance from *a tree grew*
to *the right crew fixed the right span, verifiably*, and (b) keep the
**human-in-the-loop guardrail** explicit — because utilities buy *augmentation,
not autonomy*, in a wildfire-liability world.
([GE Vernova on predictive-VM expectations](https://www.gevernova.com/software/blog/predictive-utility-vegetation-management-myths))

---

## 2. Roadmap

### NEAR — 0–1 year (extend what exists)

- **Sensor ingest adapters.** A typed ingest seam for LiDAR, multispectral/NDVI,
  thermal, and satellite change-detection tiles — the same data classes Davey
  already captures with Skydio drones and **FAA BVLOS** long-corridor flights.
  ([Davey BVLOS waivers](https://www.davey.com/about/newsroom/davey-resource-group-granted-faa-bvlos-waivers/))
- **Grow-in / fall-in risk scoring** at span level from clearance-vs-conductor,
  species growth rate, slope (we already compute terrain slope), and outage
  history — surfaced as a ranked queue, **reviewed and signed by a forester.**
  ([Utility Analytics Institute](https://utilityanalytics.com/using-machine-learning-to-improve-vegetation-management-in-power-line-corridors/))
- **Reliability tie-out.** Connect attainment + verified outcomes to
  **SAIDI / SAIFI / CMI**, the metrics utilities actually manage to.
- **NERC FAC-003 + Wildfire compliance pack.** One-click evidence bundles;
  ready for the proposed expansion of FAC-003 to **≥100 kV**.
  ([NERC 2026 wildfire filing](https://www.nerc.com/globalassets/who-we-are/legal--regulatory/filings--orders/nerc-filings-to-ferc/2026/wildfire-report-filing_signed.pdf))

### MID — 1–3 years (close the sensing→dispatch loop)

- **Multi-sensor fusion → work list.** Fuse satellite cadence with LiDAR
  precision for near-monthly change detection (the pattern AiDash, Overstory,
  LiveEO, Neara, Sharper Shape are productizing) into a prioritized, **planner-
  approved** work list. ([AiDash](https://www.aidash.com/intelligent-vegetation-management/), [Overstory](https://www.overstory.com/solutions))
- **The AI copilot (human-reviewed).** A recommendation card that ranks a span
  and **explains itself in plain language** — "high because fast-growing species
  + 3 ft clearance + high wind exposure + prior outage" — always exposing the
  underlying evidence, never asserting a verdict. Low-confidence classifications
  route to human QA. *AI does not authorize a cut, a herbicide, or a closure.*
- **Wildfire ignition-risk layer.** Composite HFTD/HFRA ignition scoring +
  fuel-moisture from multispectral, in the spirit of SDG&E **FireSight** — as an
  input to human de-energization/prioritization, never the decision.
  ([SDG&E FireSight](https://www.sdge.com/sites/default/files/regulatory/SDG&E%20-Risk-4%20Wildfire%20&%20PSPS_0.pdf))
- **Two-way SAP + GIS fabric.** OData services into **SAP S/4HANA** (WBS/CATS,
  work orders) and a GIS system of record, with the field app staying
  offline-first — matching how utility Angular teams integrate.

### LONG — 3–5 years (the living model)

- **Physics-aware digital twin** of conductors + vegetation that simulates sag,
  clearance, and encroachment per span under wind/drought/fire scenarios, and
  predicts **species-specific regrowth** ("what will clearance look like in 18
  months, wet year vs drought"). This is the Neara direction, applied to the
  outcome record. ([Neara](https://neara.com/physics-enabled-digital-twin/))
- **Condition-based cycles.** Replace fixed trim cycles with twin-driven,
  risk-ranked scheduling — the shift CenterPoint's resiliency program credits
  with a reported **~50% year-over-year cut in vegetation-related outage
  minutes.** ([Utility Analytics Institute](https://utilityanalytics.com/ai-powered-vegetation-management/))
- **Always-on monitoring.** Persistent IoT + scheduled autonomous BVLOS flights
  feed the twin continuously; the loop closes: *detect → rank → human-approve →
  dispatch → verify outcome → re-score.*

---

## 3. The AI-engineer plan (and its hard boundary)

AI in CanopyOps is an **augmentation layer**, scoped deliberately:

**AI may:** rank spans by risk, cluster and classify imagery, predict regrowth,
draft a plain-language *explanation* of why something ranked high, summarize an
audit trail, and pre-fill a form for a human to check.

**AI may never:** authorize a cut, prescribe a herbicide or rate, declare a site
effective/safe/compliant, approve a closure, or trigger a de-energization. Those
stay with certified arborists, planners, compliance reviewers, and operators —
evidence-linked and signed. Every AI output must show its evidence, carry a
confidence, and be reversible.

This isn't a limitation bolted on; it's the product's spine. It's the responsible
framing *and* the credible one — and it's exactly why an assurance system, not an
autonomy system, is what wins trust.

---

## 4. How we measure it

Outcome attainment · verified-effective rate · evidence-completeness · rework
rate · **SAIDI / SAIFI / CMI** deltas on managed circuits · NERC clearance
compliance · HFTD risk-weighted completion · time from *detected* to *verified
fixed*.

---

## 5. Honest boundaries

Synthetic data only. No real LiDAR/SAP/GIS/GPS feeds — the adapter seams are
shown, not wired to a utility. Vendor-reported outcomes (e.g., the CenterPoint
figure) are cited as such. Public sources emphasize Davey's **open-source GIS**;
we do **not** assume Esri or SAP internally. This document is a design vision, not
a claim of delivery.

*See the animated companion at `/vision` in the app.*
