# Literature review: single-channel speech enhancement (2021 – 2025)

> Numbers are **as reported by the authors** on VoiceBank-DEMAND (VB-D) unless noted.
> Venue ranks: IEEE/ACM TASLP is a Q1 journal; Interspeech is CORE A; NeurIPS and ICLR are CORE A\*.
> Check every citation and rank against the official sources before submitting.

## 1. How the problem is solved today

Speech enhancement (SE) recovers clean speech `s` from a noisy mixture `y = s + n`. Current work falls into three groups:

| Group | Idea | Typical models | Strengths | Weaknesses |
|---|---|---|---|---|
| **Discriminative, T-F domain** | Predict a mask or a spectrum from the STFT | MetricGAN+, CMGAN, MP-SENet, SEMamba, DeepFilterNet | Best PESQ on VB-D, small (~2 M params), fast | Can leave over-suppression artefacts; phase is hard to model; may not generalise beyond the training noise |
| **Generative (diffusion / score-based)** | Learn the distribution of clean speech, sample it given the noisy input | SGMSE+, StoRM, DOSE | Natural-sounding output, robust to unseen conditions, also handles dereverberation | Many network evaluations per utterance (slow); can hallucinate phonemes at low SNR; lower PESQ than the best discriminative models |
| **Language-model / token-based** | Turn speech into discrete codec / SSL tokens, then predict clean tokens with an LM | SELM, MaskSR, GenSE | Strong in real-world, multi-distortion conditions; one model for many tasks | Very large; output can drift from the speaker or content; intrusive metrics such as PESQ penalise them |

Trends: (i) **explicit phase modelling** (magnitude + phase in parallel, anti-wrapping losses); (ii) **metric-oriented training** (a discriminator that learns PESQ); (iii) **two-stage time/frequency sequence modelling** (Conformer → Mamba); (iv) **generative models** for robustness; (v) **real-time / low-complexity** designs for devices (DeepFilterNet).

**Vietnam:** we found few dedicated SE papers in Q1/Q2 venues. Most Vietnamese work deals with noise as part of other tasks: noise-augmented training for Vietnamese ASR (e.g. a 2025 *Tạp chí Khoa học* paper that mixes 2000 h of real Vietnamese noise into a 200 h corpus) and denoising found data for TTS (VLSP 2020/2021 systems). Front-end SE for Vietnamese speech, where there is no public VB-D-style corpus, is still largely open. *(Add any domestic papers your group knows.)*

## 2. Selected papers

### P1. CMGAN: Conformer-based Metric GAN for Monaural Speech Enhancement
*S. Abdulatif, R. Cao, B. Yang. IEEE/ACM TASLP, vol. 32, 2024 (Q1). Short version at Interspeech 2022.*
- **Method:** a dense encoder, four two-stage Conformer blocks (time, then frequency), and two decoders: a magnitude mask and a complex refinement. Trained with a MetricGAN discriminator that predicts PESQ.
- **Results:** PESQ 3.41, CSIG 4.63, CBAK 3.94, COVL 4.12, SSNR 11.10, STOI 0.96, 1.83 M params.
- **+** Strong results with a small model; the TF-Conformer models both time and frequency context; the paper is thorough (denoising, dereverberation, super-resolution).
- **−** The complex branch only refines the noisy phase, so phase is still estimated indirectly. Attention is quadratic in utterance length, the model is non-causal, and computing PESQ for the GAN slows training.

### P2. MP-SENet: Parallel Denoising of Magnitude and Phase Spectra *(the solution we analyse in depth)*
*Y.-X. Lu, Y. Ai, Z.-H. Ling. Interspeech 2023 (CORE A). Extended version: "Explicit estimation of magnitude and phase spectra in parallel for high-quality speech enhancement", Neural Networks, 2025.*
- **Method:** the same encoder and TF-Conformer backbone, with **two parallel decoders**: a magnitude-mask decoder (learnable sigmoid, β = 2) and a **phase decoder** that predicts pseudo real/imag parts and takes `atan2`, so phase is estimated *explicitly*. Losses: magnitude MSE, **anti-wrapping phase losses** (instantaneous phase, group delay, instantaneous angular frequency), complex MSE, time L1, STFT consistency and a metric-discriminator loss.
- **Results:** PESQ 3.50, CSIG 4.73, CBAK 3.95, COVL 4.22, STOI 0.96, about 2.05 M params.
- **+** State of the art among ~2 M-parameter models; it is the first to estimate phase directly with wrapping-aware losses; official code and checkpoints are available.
- **−** Six loss terms with hand-tuned weights; non-causal and has quadratic attention; it only learns from VB-D noise types; PESQ-driven training can over-fit the metric.

### P3. SGMSE+: Speech Enhancement and Dereverberation with Diffusion-based Generative Models
*J. Richter, S. Welker, J.-M. Lemercier, B. Lay, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023 (Q1).*
- **Method:** a score-based diffusion model in the complex STFT domain. A stochastic differential equation drifts from clean speech towards the noisy mixture, and a predictor–corrector sampler runs it in reverse, conditioned on the noisy input. The backbone is NCSN++.
- **Results:** PESQ 2.93, ESTOI 0.87, SI-SDR 17.3 dB on VB-D; it works better on mismatched test sets (trained on WSJ0-CHiME3, tested on VB-D).
- **+** Generalises well and sounds natural; the same model also dereverberates.
- **−** About 60 network evaluations per utterance with a roughly 65 M-parameter network, so it is slow; it can produce breathing or phoneme artefacts at low SNR; its PESQ is below the best discriminative models.

### P4. StoRM: A Diffusion-based Stochastic Regeneration Model
*J.-M. Lemercier, J. Richter, S. Welker, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023 (Q1).*
- **Method:** a predictive (discriminative) model first gives an estimate, then a diffusion model *regenerates* the details from it. This combines the strengths of the two families.
- **+** Removes the vocalising/breathing artefacts of pure diffusion and needs far fewer sampling steps than SGMSE+.
- **−** Two networks to train and run; still slower than a single predictive model.

### P5. DOSE: Diffusion Dropout with Adaptive Prior for Speech Enhancement
*W. Tai, Y. Lei, F. Zhou, G. Trajcevski, T. Zhong. NeurIPS 2023 (CORE A\*).*
- **Method:** fixes the weak condition in conditional diffusion SE. *Diffusion dropout* during training makes the model rely on the noisy condition, and an *adaptive prior* starts sampling from a noisy estimate instead of pure noise. It needs only two sampling steps.
- **+** Efficient diffusion SE with good generalisation and theoretical analysis.
- **−** Its PESQ on VB-D is still well below discriminative SOTA; the method is complex to tune.

### P6. GenSE: Generative Speech Enhancement via Language Models using Hierarchical Modeling
*J. Yao, H. Liu, C. Chen, Y. Hu, E. S. Chng, L. Xie. ICLR 2025 (CORE A\*).*
- **Method:** SE as conditional language modelling. Semantic tokens from a self-supervised model and acoustic tokens from a single-quantiser codec are predicted in two hierarchical stages (noisy→clean semantic, then semantic→acoustic), with token-chain prompting to keep the speaker's timbre.
- **+** Strong DNSMOS and speaker similarity on real recordings; robust to many distortions.
- **−** Large model and slow autoregressive decoding; reported mostly on DNS-style non-intrusive metrics; risk of content or speaker drift.

### Additional related work
- **MetricGAN+** (Fu et al., Interspeech 2021): a BLSTM mask with a learned PESQ discriminator, PESQ 3.15. It is the origin of the metric discriminator used in P1/P2.
- **DeepFilterNet** (Schröter et al., ICASSP 2022; v2/v3 follow-ups): ERB-band gains plus *deep filtering* for real-time full-band (48 kHz) SE with very low complexity; around 3.1 PESQ on VB-D for v2/v3.
- **SEMamba** (Chao et al., IEEE SLT 2024): replaces the Conformers of MP-SENet with Mamba (state-space) blocks, giving linear-time sequence modelling; PESQ 3.55, or 3.69 with perceptual contrast stretching (PCS). This motivates our proposed **PCS** improvement.

## 3. Summary table (VB-D, as reported)

| Model | Venue | Type | PESQ | CSIG | CBAK | COVL | STOI | Params |
|---|---|---|---|---|---|---|---|---|
| Noisy | – | – | 1.97 | 3.35 | 2.44 | 2.63 | 0.91 | – |
| MetricGAN+ | Interspeech'21 | Disc. mask | 3.15 | 4.14 | 3.16 | 3.64 | – | – |
| SGMSE+ | TASLP'23 | Diffusion | 2.93 | – | – | – | ESTOI 0.87 | ~65 M |
| CMGAN | TASLP'24 | Disc. mag+complex | 3.41 | 4.63 | 3.94 | 4.12 | 0.96 | 1.83 M |
| MP-SENet | Interspeech'23 | Disc. mag+phase | 3.50 | 4.73 | 3.95 | 4.22 | 0.96 | 2.05 M |
| SEMamba (+PCS) | SLT'24 | Disc. (Mamba) | 3.55 (3.69) | – | – | – | – | ~2 M |
