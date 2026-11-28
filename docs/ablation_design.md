# Ablation study design and in-depth analysis of MP-SENet

## 1. Why MP-SENet

MP-SENet is the strongest *small* discriminative model with official code. Its design combines most of
the current trends: TF-Conformers, explicit phase, metric-GAN training and multi-domain losses. It is also
the backbone that later work (SEMamba and others) builds on. So asking "which of these parts really
matters?" is useful well beyond this one model.

## 2. Model recap (our re-implementation, `src/se/models/generator.py`)

```
noisy wav ─STFT─► |Y|^0.3 , ∠Y ──► DenseEncoder (1×1 conv, dilated DenseBlock, freq ↓2)
                                   │
                                   ▼
                       4 × TS-Conformer (time-Conformer → freq-Conformer)
                         ┌─────────┴──────────┐
              Magnitude decoder          Phase decoder
              (DenseBlock, freq ↑2,       (DenseBlock, freq ↑2,
               learnable sigmoid β=2)      r, i  → atan2(i, r))
                   mask × |Y|^0.3              ∠Ŝ
                         └────────► iSTFT ◄────┘
```
2.047 M parameters (the paper reports 2.05 M). n_fft = 400, hop = 100, compression c = 0.3, 2 s segments, batch 4,
AdamW (lr 5e-4, β = (0.8, 0.99)), lr × 0.99 per epoch.

Loss = 0.9·L_mag + 0.3·(L_IP + L_GD + L_IAF) + 0.1·L_com + 0.2·L_time + 0.1·L_consistency + 0.05·L_metric.

## 3. Protocol

* **Data:** VoiceBank-DEMAND at 16 kHz. Speakers p226 and p287 (≈ 770 utterances) are **held out from the 28 training
  speakers for validation and model selection**. The official 824-utterance test set is used **only once**, for the
  final numbers. (The reference code selects models on the test set, which inflates scores slightly.)
* **Metrics:** PESQ-wb, CSIG, CBAK, COVL, SSNR, STOI, ESTOI, SI-SDR, parameter count and real-time factor.
* **One factor at a time:** every config in `configs/ablation/` inherits `configs/base.yaml` and changes exactly one factor.
* **Same budget:** same epochs, seed, and selection rule (best validation PESQ) for every run.
* **Significance (recommended):** if compute allows, repeat the baseline and the closest runs with 2–3 seeds
  (`experiment.seed=…`) and report mean ± std. A paired t-test / Wilcoxon on `per_file.csv` checks whether ΔPESQ is
  significant.

## 4. Experiments

With a limited GPU budget (10 epochs per run, one GPU at a time) we run **one ablation per main idea** of
MP-SENet: the training signal (a01), phase supervision (a02), the phase decoder itself (a05, the paper's core
claim) and the backbone (a09), plus the two proposals P1 and P2 (`configs/experiments.txt`). The others are
implemented and kept as future work (`configs/experiments_full.txt` runs all of them).

**Run:**

| ID | Factor removed / changed | Question it answers |
|---|---|---|
| a00 | — (full model) | reference |
| a01 | no metric discriminator (`loss.metric=0`) | How much does PESQ-driven GAN training add? Is it only metric over-fitting (check STOI/SI-SDR)? |
| a02 | no phase losses | Can the phase decoder learn useful phase without explicit anti-wrapping supervision? |
| a05 | magnitude-only decoder, noisy phase | **Core claim of the paper:** value of explicit phase estimation |
| a09 | BiLSTM instead of Conformer | Attention + convolution vs. recurrent sequence modelling |

**Future work (implemented, not run):**

| ID | Factor removed / changed | Question it answers |
|---|---|---|
| a03 | no STFT-consistency loss | Does enforcing a consistent spectrogram matter? |
| a04 | no time L1 + complex losses | Value of the waveform- and complex-domain terms |
| a06 | single complex-mapping decoder | Parallel mag + phase vs. the common complex-spectrum mapping |
| a07 | no magnitude compression (c = 1) | Effect of power-law compression on the dynamic range |
| a08 | 2 instead of 4 TS-Conformer blocks | Depth vs. quality / speed trade-off |
| a10 | plain sigmoid mask (β = 1) | Learnable sigmoid with β = 2 lets the mask amplify (> 1) |
| p03 | P1 + P2 combined | Do the two proposals add up? |

## 5. Proposed improvements (part 4 of the assignment)

1. **P1 – Multi-resolution STFT loss** (`loss.mrstft=0.1`). The paper's losses all work at one STFT resolution
   (400/100). A multi-resolution spectral-convergence + log-magnitude loss at (256, 512, 1024)-point FFTs
   penalises artefacts that the 25 ms analysis window misses, such as pre-echo and smeared transients, and
   regularises the waveform output. It adds no inference cost.
2. **P2 – Perceptual contrast stretching (PCS) of the training target** (`data.pcs=true`). The clean target is
   made sharper in the bands that matter most for intelligibility (SII band-importance gains 1.0–1.4 on log1p
   magnitude). SEMamba reports +0.14 PESQ from PCS on a Mamba backbone; we test whether this carries over to the
   Conformer backbone. It also adds no inference cost.
3. **P3 – P1 + P2 combined** (future work: only worthwhile if P1 and P2 each help).

Further ideas, discussed but not implemented because of the compute budget: Mamba blocks instead of Conformers
(linear complexity, as in SEMamba); a causal / streaming variant with chunked attention for real-time use; and
training on DNS-Challenge data to test generalisation beyond VB-D noise.

## 6. How to read the results

* ΔPESQ around ±0.03 is usually within seed noise on VB-D; after only 10 epochs, treat < 0.05 as inconclusive. Look at CSIG/CBAK/COVL/STOI/SI-SDR together.
* For the GAN ablation (a01), PESQ is expected to drop while SI-SDR may *rise*: the discriminator optimises perceived
  quality, not waveform fidelity. Report both.
* For phase ablations (a02, a05), listen to the outputs: noisy-phase artefacts sound "rough" or "robotic" even when
  PESQ changes little.
