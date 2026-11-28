# Tăng cường tiếng nói: nghiên cứu ablation MP-SENet

Đồ án cuối kỳ môn **Xử lý tiếng nói** (Trường ĐH Khoa học Tự nhiên, ĐHQG-HCM, chương trình Thạc sĩ), hướng nghiên cứu.

Giảng viên: PGS.TS. Đinh Điền, TS. Châu Thành Đức.

Repository gồm:

1. **Khảo sát tài liệu** các bài báo tăng cường tiếng nói (speech enhancement) gần đây (TASLP, Interspeech, NeurIPS, ICLR): xem [`docs/literature_review.md`](docs/literature_review.md)
2. **Demo:** làm sạch tiếng nói bằng mô hình đã huấn luyện (`se.enhance`), notebook nghe và so sánh các lần chạy ablation, và script chạy checkpoint chính thức của MP-SENet để tham chiếu ([`scripts/demo_official_mpsenet.sh`](scripts/demo_official_mpsenet.sh))
3. **Nghiên cứu ablation:** cài đặt lại MP-SENet (Lu et al., Interspeech 2023) với các công tắc cấu hình cho 10 ablation, trong đó 4 ablation chính được chạy: [`docs/ablation_design.md`](docs/ablation_design.md)
4. **Đề xuất cải tiến:** loss multi-resolution STFT và perceptual contrast stretching (PCS) cho mục tiêu huấn luyện, được đánh giá giống như các ablation

Báo cáo: [`docs/report/report.pdf`](docs/report/report.pdf) · Slide: [`docs/slides/slides.pdf`](docs/slides/slides.pdf)

## Thành viên

| MSHV | Họ tên | Công việc |
|---|---|---|
| 25C15036 | Chau Kien Dat | khảo sát tài liệu, demo, slide, viết báo cáo |
| 25C15043 | Nguyen Vi Khang | cài đặt lại mô hình, chạy ablation trên HPC, đánh giá, video |

## Cấu trúc repository

```
se-ablation/
├── configs/
│   ├── base.yaml               # baseline đầy đủ kiểu MP-SENet (a00)
│   ├── debug.yaml              # chạy thử nhỏ trên CPU
│   ├── experiments.txt         # 7 lần chạy chính dùng cho SLURM array / chạy local
│   ├── experiments_full.txt    # cả 14 lần chạy (gồm các ablation để lại cho hướng phát triển)
│   └── ablation/               # ablation a01–a10, cải tiến đề xuất p01–p03 (mỗi file một yếu tố)
├── src/se/
│   ├── data/                   # dataset VoiceBank-DEMAND theo cặp, tách người nói làm validation
│   ├── models/                 # generator (dense encoder, TS-Conformer, decoder biên độ/pha), metric discriminator
│   ├── losses/                 # magnitude, pha anti-wrapping, complex, time, consistency, metric-GAN, MR-STFT
│   ├── metrics/                # PESQ, CSIG/CBAK/COVL, SSNR, STOI/ESTOI, SI-SDR
│   ├── utils/                  # hệ thống cấu hình, STFT, PCS
│   ├── train.py                # huấn luyện (một GPU hoặc DDP qua torchrun), tự động tiếp tục
│   ├── evaluate.py             # đánh giá toàn bộ tập test -> per_file.csv + summary.json
│   ├── enhance.py              # tăng cường một file wav / thư mục bất kỳ
│   └── inference.py
├── scripts/
│   ├── prepare_vbd.py          # tải + resample VoiceBank-DEMAND về 16 kHz
│   ├── make_dummy_data.py      # dữ liệu tổng hợp để chạy thử
│   ├── run_ablation_local.sh   # chạy lần lượt mọi thí nghiệm (không cần SLURM)
│   ├── collect_results.py      # -> results/ablation_results.{csv,md}, ablation_pesq.png
│   ├── score_dir.py            # chấm điểm một thư mục wav đã tăng cường bằng metric của nhóm
│   └── demo_official_mpsenet.sh
├── slurm/                      # script sbatch cho HPC (chạy đơn, job array, DDP, baseline đầu vào nhiễu)
├── notebooks/demo.ipynb        # nghe + spectrogram + metric cho một vài câu
├── docs/                       # khảo sát tài liệu, thiết kế ablation, báo cáo, slide
├── results/                    # kết quả tổng hợp (điền sau khi huấn luyện)
└── tests/                      # unit test pytest (kích thước tensor, loss, metric, cấu hình)
```

## 1. Cài đặt

```bash
git clone <this-repo-url> se-ablation && cd se-ablation
python -m venv .venv && source .venv/bin/activate          # hoặc: conda env create -f environment.yml
pip install torch --index-url https://download.pytorch.org/whl/cu121   # chọn đúng phiên bản CUDA
pip install -e ".[dev]"
pytest -q                                                   # 21 test, chỉ cần CPU
```

`pesq` được build từ mã nguồn và cần trình biên dịch C (`gcc` trên Linux; *MSVC Build Tools* trên Windows). Nếu `gcc`
quá cũ (ví dụ 4.8), dùng `CFLAGS="-std=gnu99" pip install -e ".[dev]"`.

## 2. Dữ liệu

```bash
python scripts/prepare_vbd.py --out data      # tải khoảng 2.5 GB, resample 48 kHz -> 16 kHz
```
Lệnh này tạo `data/voicebank_demand_16k/{clean,noisy}_{trainset_28spk,testset}_wav/`. Nếu URL tải thay đổi, tải thủ công
bốn file zip từ https://datashare.ed.ac.uk/handle/10283/2791 vào `data/raw/` rồi chạy script với `--skip_download`.

## 3. Chạy thử (CPU, khoảng một phút trên máy thường)

```bash
python scripts/make_dummy_data.py --out data/dummy
python -m se.train --config configs/debug.yaml
```

## 4. Huấn luyện và ablation

Mọi giá trị cấu hình đều có thể ghi đè từ dòng lệnh bằng khóa dạng dấu chấm.

```bash
# một lần chạy (tự đánh giá best.pt trên tập test khi xong)
python -m se.train --config configs/base.yaml
python -m se.train --config configs/ablation/a03_mag_only.yaml train.epochs=50

# nhiều GPU trên một node (batch_size tính cho mỗi GPU)
torchrun --standalone --nproc_per_node=4 -m se.train --config configs/base.yaml
```

### Trên cụm HPC (SLURM)

`slurm/env.sh` kích hoạt `./.venv` nếu có, nếu không thì kích hoạt môi trường conda `hcmus-sh` (đổi bằng `CONDA_ENV=...`).
Thêm các dòng `module load` mà cụm cần vào đó. Sau đó sửa dòng partition `#SBATCH` (hoặc truyền `-p <partition>`) và chạy:

```bash
sbatch slurm/eval_noisy.sbatch                         # dòng tham chiếu: đầu vào nhiễu chưa xử lý
sbatch --array=0-6%1 slurm/ablation_array.sbatch       # 7 lần chạy chính (configs/experiments.txt), mỗi lần một job
EPOCHS=30 sbatch --array=0-6%1 slurm/ablation_array.sbatch   # huấn luyện lâu hơn (mặc định: 5 epoch)
EXPERIMENTS=configs/experiments_full.txt sbatch --array=0-13%1 slurm/ablation_array.sbatch   # cả 14, gồm hướng phát triển
```
Job tự động tiếp tục từ `runs/<name>/checkpoints/last.pt`, nên job nào chạm giới hạn thời gian chỉ cần gửi lại.

**Ước lượng thời gian:** mặc định mỗi lần chạy huấn luyện 5 epoch (`train.epochs` trong `configs/base.yaml`): khoảng
1.5 giờ trên A100 hoặc 3–4 giờ trên P100 với các lần chạy có metric GAN (11.5k đoạn 2 s, batch 4). PESQ cho discriminator
được tính song song trên CPU (`train.pesq_workers`), nên mỗi job cần ít nhất 8 CPU core. Bài báo huấn luyện lâu hơn nhiều
nên điểm tuyệt đối thấp hơn, nhưng mọi lần chạy có cùng ngân sách.

### Tổng hợp kết quả

```bash
python scripts/collect_results.py      # -> results/ablation_results.csv / .md / ablation_pesq.png
```

## 5. Đánh giá, suy luận và demo

```bash
python -m se.evaluate --ckpt runs/a00_baseline/checkpoints/best.pt --save_wavs
python -m se.enhance  --ckpt runs/a00_baseline/checkpoints/best.pt --input my_noisy.wav --output out/

# nghe và so sánh các lần chạy ablation
jupyter notebook notebooks/demo.ipynb

# mã nguồn + checkpoint chính thức của MP-SENet, chấm bằng bộ metric của nhóm (tham chiếu)
bash scripts/demo_official_mpsenet.sh data/voicebank_demand_16k
```

## 6. Các thí nghiệm

Các lần chạy chính (`configs/experiments.txt`, 7 lần): mỗi ý tưởng chính của MP-SENet một ablation, cộng hai đề xuất.

| ID | Thay đổi so với baseline |
|---|---|
| a00 | mô hình đầy đủ (kiểu MP-SENet, 2.05 M tham số) |
| a01 | bỏ metric discriminator |
| a02 | bỏ các loss pha anti-wrapping |
| a03 | decoder chỉ biên độ (dùng pha nhiễu) |
| a04 | BiLSTM thay cho Conformer |
| p01 | **+ loss multi-resolution STFT** (đề xuất) |
| p02 | **+ mục tiêu PCS** (đề xuất) |

Hướng phát triển: đã cài đặt, mỗi thí nghiệm một file cấu hình, chưa chạy trong ngân sách hiện tại
(`configs/experiments_full.txt` chạy tất cả): a05 bỏ loss nhất quán STFT · a06 bỏ loss thời gian + phức ·
a07 decoder ánh xạ phức · a08 không nén biên độ (c = 1) · a09 2 khối TS-Conformer · a10 mask sigmoid thường ·
p03 kết hợp P1 + P2.

Bảng kết quả được sinh vào `results/ablation_results.md` sau khi các lần chạy hoàn tất. Để đưa số liệu vào slide, chạy
`python docs/slides/build_slides.py` (đọc file CSV đó), rồi xuất PDF (xem `docs/slides/README.md`).

## 7. Build lại báo cáo và slide

Cả hai được sinh từ mã nguồn và tự điền kết quả từ `results/ablation_results.csv`.

```bash
pip install -e ".[slides]"
python docs/report/build_report.py                      # hình + docs/report/report.docx
powershell -File docs/report/export_pdf.ps1             # Windows + Word: cập nhật mục lục, xuất report.pdf
```

```bash
python docs/slides/build_slides.py                      # -> docs/slides/slides.pptx (điền bảng từ results/ nếu có)
powershell -File docs/slides/export_pdf.ps1             # Windows + PowerPoint -> slides.pdf
# hoặc: soffice --headless --convert-to pdf docs/slides/slides.pptx --outdir docs/slides
```

## Tài liệu tham khảo

* Y.-X. Lu, Y. Ai, Z.-H. Ling, *MP-SENet: A Speech Enhancement Model with Parallel Denoising of Magnitude and Phase Spectra*, Interspeech 2023. Mã nguồn chính thức: https://github.com/yxlu-0102/MP-SENet. Repository này là bản cài đặt lại độc lập phục vụ ablation.
* S. Abdulatif, R. Cao, B. Yang, *CMGAN: Conformer-Based Metric-GAN for Monaural Speech Enhancement*, IEEE/ACM TASLP 2024.
* R. Chao et al., *An Investigation of Incorporating Mamba for Speech Enhancement*, IEEE SLT 2024 (PCS).
* C. Valentini-Botinhao et al., *Investigating RNN-based speech enhancement methods for noise-robust Text-to-Speech*, SSW 2016 (VoiceBank-DEMAND).
* Composite measures: Y. Hu, P. Loizou, *Evaluation of objective quality measures for speech enhancement*, IEEE TASLP 2008.

Giấy phép MIT.
