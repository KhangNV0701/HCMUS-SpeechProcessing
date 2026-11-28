# Thiết kế nghiên cứu ablation và phân tích chuyên sâu MP-SENet

## 1. Vì sao chọn MP-SENet

MP-SENet là mô hình discriminative *nhỏ* mạnh nhất có mã nguồn chính thức. Thiết kế của nó kết hợp phần lớn các xu hướng
hiện nay: TF-Conformer, pha tường minh, huấn luyện metric-GAN và loss đa miền. Đây cũng là backbone mà các công trình sau
(SEMamba và các mô hình khác) xây dựng dựa trên. Vì vậy câu hỏi "thành phần nào thực sự quan trọng?" có ích vượt ra ngoài
riêng mô hình này.

## 2. Tóm tắt mô hình (bản cài đặt lại, `src/se/models/generator.py`)

```
wav nhiễu ─STFT─► |Y|^0.3 , ∠Y ──► DenseEncoder (conv 1×1, DenseBlock giãn, tần số ↓2)
                                   │
                                   ▼
                       4 × TS-Conformer (Conformer thời gian → Conformer tần số)
                         ┌─────────┴──────────┐
              Decoder biên độ             Decoder pha
              (DenseBlock, tần số ↑2,     (DenseBlock, tần số ↑2,
               sigmoid học được β=2)       r, i  → atan2(i, r))
                   mask × |Y|^0.3              ∠Ŝ
                         └────────► iSTFT ◄────┘
```
2.047 M tham số (bài báo báo cáo 2.05 M). n_fft = 400, hop = 100, hệ số nén c = 0.3, đoạn 2 s, batch 4,
AdamW (lr 5e-4, β = (0.8, 0.99)), lr × 0.99 sau mỗi epoch.

Loss = 0.9·L_mag + 0.3·(L_IP + L_GD + L_IAF) + 0.1·L_com + 0.2·L_time + 0.1·L_consistency + 0.05·L_metric.

## 3. Quy trình

* **Dữ liệu:** VoiceBank-DEMAND ở 16 kHz. Người nói p226 và p287 (≈ 770 câu) được **tách khỏi 28 người nói huấn luyện để
  làm validation và chọn mô hình**. Tập test chính thức 824 câu **chỉ được dùng một lần**, cho kết quả cuối cùng. (Mã gốc
  chọn mô hình trên tập test, làm điểm bị thổi phồng nhẹ.)
* **Metric:** PESQ-wb, CSIG, CBAK, COVL, SSNR, STOI, ESTOI, SI-SDR, số tham số và real-time factor.
* **Mỗi lần một yếu tố:** mọi cấu hình trong `configs/ablation/` kế thừa `configs/base.yaml` và đổi đúng một yếu tố.
* **Cùng ngân sách:** cùng số epoch, seed và quy tắc chọn mô hình (PESQ validation tốt nhất) cho mọi lần chạy.
* **Ý nghĩa thống kê (khuyến nghị):** nếu đủ tài nguyên, chạy lại baseline và các lần chạy sát nhau với 2–3 seed
  (`experiment.seed=…`) và báo cáo trung bình ± độ lệch chuẩn. Paired t-test / Wilcoxon trên `per_file.csv` kiểm tra
  ΔPESQ có ý nghĩa hay không.

## 4. Các thí nghiệm

Do giới hạn GPU (5 epoch mỗi lần chạy, mỗi lần một GPU), chúng tôi chạy **một ablation cho mỗi ý tưởng chính** của
MP-SENet: tín hiệu huấn luyện (a01), giám sát pha (a02), bản thân decoder pha (a03, luận điểm cốt lõi của bài báo) và
backbone (a04), cộng hai đề xuất P1 và P2 (`configs/experiments.txt`). Các ablation còn lại đã được cài đặt và để lại cho
hướng phát triển (`configs/experiments_full.txt` chạy tất cả).

**Đã chạy:**

| ID | Yếu tố bị bỏ / thay đổi | Câu hỏi cần trả lời |
|---|---|---|
| a00 | — (mô hình đầy đủ) | tham chiếu |
| a01 | bỏ metric discriminator (`loss.metric=0`) | Huấn luyện GAN theo PESQ đóng góp bao nhiêu? Có phải chỉ overfit metric (kiểm tra STOI/SI-SDR)? |
| a02 | bỏ các loss pha | Decoder pha có học được pha hữu ích khi không có giám sát anti-wrapping tường minh? |
| a03 | decoder chỉ biên độ, dùng pha nhiễu | **Luận điểm cốt lõi của bài báo:** giá trị của ước lượng pha tường minh |
| a04 | BiLSTM thay cho Conformer | Attention + tích chập so với mô hình chuỗi hồi quy (recurrent) |

**Hướng phát triển (đã cài đặt, chưa chạy):**

| ID | Yếu tố bị bỏ / thay đổi | Câu hỏi cần trả lời |
|---|---|---|
| a05 | bỏ loss nhất quán STFT | Ép spectrogram nhất quán có quan trọng không? |
| a06 | bỏ loss L1 thời gian + loss phức | Giá trị của các thành phần trên dạng sóng và miền phức |
| a07 | một decoder ánh xạ phổ phức | Biên độ + pha song song so với ánh xạ phổ phức thông dụng |
| a08 | không nén biên độ (c = 1) | Ảnh hưởng của nén lũy thừa lên dải động |
| a09 | 2 thay vì 4 khối TS-Conformer | Đánh đổi độ sâu với chất lượng / tốc độ |
| a10 | mask sigmoid thường (β = 1) | Sigmoid học được với β = 2 cho phép mask khuếch đại (> 1) |
| p03 | kết hợp P1 + P2 | Hai đề xuất có cộng dồn hiệu quả? |

## 5. Đề xuất cải tiến (phần 4 của đồ án)

1. **P1 – Loss multi-resolution STFT** (`loss.mrstft=0.1`). Các loss trong bài báo đều làm việc ở một độ phân giải STFT
   (400/100). Một loss spectral convergence + log-magnitude đa phân giải ở FFT (256, 512, 1024) điểm phạt các lỗi mà cửa
   sổ phân tích 25 ms bỏ sót, như pre-echo và transient bị nhòe, đồng thời điều chuẩn dạng sóng đầu ra. Không tốn thêm chi
   phí suy luận.
2. **P2 – Perceptual contrast stretching (PCS) cho mục tiêu huấn luyện** (`data.pcs=true`). Mục tiêu sạch được làm sắc nét
   hơn ở các dải quan trọng nhất cho độ dễ hiểu (hệ số band-importance SII 1.0–1.4 trên log1p magnitude). SEMamba báo cáo
   +0.14 PESQ nhờ PCS trên backbone Mamba; chúng tôi kiểm tra hiệu quả này có chuyển sang backbone Conformer không. Cũng
   không tốn thêm chi phí suy luận.
3. **P3 – Kết hợp P1 + P2** (hướng phát triển: chỉ đáng làm nếu P1 và P2 đều có ích khi đứng riêng).

Các ý tưởng khác đã thảo luận nhưng chưa cài đặt do giới hạn tài nguyên: khối Mamba thay cho Conformer (độ phức tạp tuyến
tính, như SEMamba); phiên bản causal / streaming với chunked attention để dùng thời gian thực; và huấn luyện trên dữ liệu
DNS-Challenge để kiểm tra khả năng tổng quát hóa ngoài nhiễu của VB-D.

## 6. Cách đọc kết quả

* ΔPESQ khoảng ±0.03 thường nằm trong dao động giữa các seed trên VB-D; sau chỉ 5 epoch, coi chênh lệch < 0.05 là chưa
  kết luận được. Xem CSIG/CBAK/COVL/STOI/SI-SDR cùng lúc.
* Với ablation GAN (a01), PESQ được kỳ vọng giảm trong khi SI-SDR có thể *tăng*: discriminator tối ưu chất lượng cảm nhận
  chứ không phải độ trung thực dạng sóng. Báo cáo cả hai.
* Với các ablation về pha (a02, a03), hãy nghe đầu ra: lỗi do pha nhiễu nghe "rè" hoặc "giống robot" ngay cả khi PESQ thay
  đổi ít.
