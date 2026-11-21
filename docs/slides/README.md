# Slides

* `slides.pdf`: the exported deck (submission file)
* `build_slides.py`: generates `slides.pptx` with python-pptx. It fills the results table and chart from
  `results/ablation_results.csv` when that file exists, and uses a real VoiceBank-DEMAND spectrogram when the data is present.
* `export_pdf.ps1`: exports PDF (and PNGs with `-Png`) with PowerPoint on Windows.
  Alternative: `soffice --headless --convert-to pdf slides.pptx`.

```bash
python scripts/collect_results.py           # after the HPC runs
python docs/slides/build_slides.py
powershell -ExecutionPolicy Bypass -File docs/slides/export_pdf.ps1
```
Speaker notes are included in the .pptx for the first slides; add your own for the video.
