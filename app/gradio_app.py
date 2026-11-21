"""Minimal web demo for the video: upload / record noisy speech, compare checkpoints.

    pip install -e ".[app]"
    python app/gradio_app.py --ckpt runs/a00_baseline/checkpoints/best.pt \
                             --ckpt runs/p03_mrstft_pcs/checkpoints/best.pt
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

from se.inference import enhance, load_model  # noqa: E402


def spectrogram_figure(signals: dict, sr: int):
    fig, axes = plt.subplots(len(signals), 1, figsize=(9, 2.4 * len(signals)), squeeze=False)
    for ax, (title, x) in zip(axes[:, 0], signals.items()):
        ax.specgram(x + 1e-9, NFFT=512, Fs=sr, noverlap=384, cmap="magma", vmin=-120)
        ax.set_title(title)
        ax.set_ylabel("Hz")
    axes[-1, 0].set_xlabel("time (s)")
    fig.tight_layout()
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", action="append", required=True, help="repeat to compare several models")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--share", action="store_true")
    args = ap.parse_args()

    import gradio as gr

    device = "cuda" if torch.cuda.is_available() else "cpu"
    models = {Path(c).parent.parent.name: load_model(c, device) for c in args.ckpt}
    sr = next(iter(models.values()))[2].data.sample_rate

    def run(audio, model_name):
        if audio is None:
            return None, None
        file_sr, x = audio
        x = x.astype(np.float32)
        if x.ndim > 1:
            x = x.mean(axis=1)
        if np.abs(x).max() > 1.0:  # int16 from the microphone / file widget
            x = x / 32768.0
        if file_sr != sr:
            g = np.gcd(file_sr, sr)
            x = resample_poly(x, sr // g, file_sr // g).astype(np.float32)
        model, stft, _ = models[model_name]
        y = enhance(model, stft, torch.from_numpy(x), sr, chunk_seconds=10).numpy()
        fig = spectrogram_figure({"noisy input": x, f"enhanced ({model_name})": y}, sr)
        return (sr, y), fig

    with gr.Blocks(title="Speech Enhancement demo") as demo:
        gr.Markdown("## MP-SENet-style speech enhancement\nUpload or record noisy speech (resampled to 16 kHz).")
        with gr.Row():
            inp = gr.Audio(sources=["upload", "microphone"], type="numpy", label="Noisy speech")
            out = gr.Audio(type="numpy", label="Enhanced speech")
        choice = gr.Dropdown(list(models), value=next(iter(models)), label="Model")
        btn = gr.Button("Enhance", variant="primary")
        plot = gr.Plot(label="Spectrograms")
        btn.click(run, [inp, choice], [out, plot])
    demo.launch(server_port=args.port, share=args.share)


if __name__ == "__main__":
    main()
