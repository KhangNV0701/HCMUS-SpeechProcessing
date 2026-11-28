# Slide

* `slides.pdf`: bộ slide đã xuất (file nộp)
* `build_slides.py`: sinh `slides.pptx` bằng python-pptx. Script tự điền bảng và biểu đồ kết quả từ
  `results/ablation_results.csv` khi file đó tồn tại, và dùng spectrogram VoiceBank-DEMAND thật khi có dữ liệu.
* `export_pdf.ps1`: xuất PDF (và PNG với `-Png`) bằng PowerPoint trên Windows.
  Cách khác: `soffice --headless --convert-to pdf slides.pptx`.

```bash
python scripts/collect_results.py           # sau khi chạy xong trên HPC
python docs/slides/build_slides.py
powershell -ExecutionPolicy Bypass -File docs/slides/export_pdf.ps1
```
File .pptx có ghi chú thuyết trình (speaker notes) cho các slide đầu; bổ sung ghi chú riêng khi quay video.
