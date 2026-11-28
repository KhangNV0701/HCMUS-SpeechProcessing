# Khảo sát tài liệu: tăng cường tiếng nói một kênh (2021 – 2025)

> Các con số là **theo công bố của tác giả** trên VoiceBank-DEMAND (VB-D) trừ khi có ghi chú khác.
> Xếp hạng nơi công bố: IEEE/ACM TASLP là tạp chí Q1; Interspeech là CORE A; NeurIPS và ICLR là CORE A\*.
> Cần đối chiếu mọi trích dẫn và xếp hạng với nguồn chính thức trước khi nộp.

## 1. Bài toán được giải quyết thế nào hiện nay

Tăng cường tiếng nói (speech enhancement, SE) khôi phục tiếng nói sạch `s` từ hỗn hợp nhiễu `y = s + n`. Các công trình
hiện nay chia thành ba nhóm:

| Nhóm | Ý tưởng | Mô hình tiêu biểu | Ưu điểm | Nhược điểm |
|---|---|---|---|---|
| **Discriminative, miền T-F** | Dự đoán mask hoặc phổ từ STFT | MetricGAN+, CMGAN, MP-SENet, SEMamba, DeepFilterNet | PESQ tốt nhất trên VB-D, nhỏ (~2 M tham số), nhanh | Có thể để lại lỗi do triệt nhiễu quá mức; khó mô hình hóa pha; có thể không tổng quát hóa ngoài nhiễu huấn luyện |
| **Mô hình sinh (diffusion / score-based)** | Học phân phối của tiếng nói sạch, lấy mẫu có điều kiện theo đầu vào nhiễu | SGMSE+, StoRM, DOSE | Đầu ra tự nhiên, bền vững với điều kiện chưa gặp, xử lý được cả tiếng vang | Nhiều lần chạy mạng cho mỗi câu (chậm); có thể ảo giác âm vị ở SNR thấp; PESQ thấp hơn mô hình discriminative tốt nhất |
| **Language model / dựa trên token** | Chuyển tiếng nói thành token codec / SSL rời rạc, rồi dự đoán token sạch bằng LM | SELM, MaskSR, GenSE | Mạnh trong điều kiện thực tế, nhiều loại méo; một mô hình cho nhiều tác vụ | Rất lớn; đầu ra có thể lệch giọng hoặc nội dung; các metric intrusive như PESQ phạt điều này |

Xu hướng: (i) **mô hình hóa pha tường minh** (biên độ + pha song song, loss anti-wrapping); (ii) **huấn luyện hướng
metric** (discriminator học PESQ); (iii) **mô hình chuỗi hai giai đoạn thời gian/tần số** (Conformer → Mamba);
(iv) **mô hình sinh** để tăng độ bền vững; (v) thiết kế **thời gian thực / độ phức tạp thấp** cho thiết bị (DeepFilterNet).

**Việt Nam:** chúng tôi tìm thấy ít bài báo SE chuyên biệt ở các nơi công bố Q1/Q2. Phần lớn công trình tại Việt Nam xử lý
nhiễu như một phần của bài toán khác: huấn luyện ASR tiếng Việt với nhiễu tăng cường (ví dụ một bài trên *Tạp chí Khoa học*
năm 2025 trộn 2000 giờ nhiễu thực tế của Việt Nam vào kho 200 giờ) và khử nhiễu dữ liệu thu thập cho TTS (các hệ thống VLSP
2020/2021). Tăng cường tiếng nói làm khâu tiền xử lý cho tiếng Việt, khi chưa có kho dữ liệu công khai kiểu VB-D, vẫn còn
là hướng mở. *(Bổ sung các bài báo trong nước mà nhóm biết.)*

## 2. Các bài báo được chọn

### P1. CMGAN: Conformer-based Metric GAN for Monaural Speech Enhancement
*S. Abdulatif, R. Cao, B. Yang. IEEE/ACM TASLP, vol. 32, 2024 (Q1). Phiên bản ngắn tại Interspeech 2022.*
- **Phương pháp:** một dense encoder, bốn khối Conformer hai giai đoạn (thời gian, rồi tần số), và hai decoder: mask biên độ và tinh chỉnh phức. Huấn luyện với discriminator MetricGAN dự đoán PESQ.
- **Kết quả:** PESQ 3.41, CSIG 4.63, CBAK 3.94, COVL 4.12, SSNR 11.10, STOI 0.96, 1.83 M tham số.
- **+** Kết quả mạnh với mô hình nhỏ; TF-Conformer mô hình hóa ngữ cảnh theo cả thời gian và tần số; bài báo đánh giá kỹ (khử nhiễu, khử vang, siêu phân giải).
- **−** Nhánh phức chỉ tinh chỉnh pha nhiễu nên pha vẫn được ước lượng gián tiếp. Attention có chi phí bậc hai theo độ dài câu, mô hình không causal, và tính PESQ cho GAN làm chậm huấn luyện.

### P2. MP-SENet: Parallel Denoising of Magnitude and Phase Spectra *(giải pháp được phân tích chuyên sâu)*
*Y.-X. Lu, Y. Ai, Z.-H. Ling. Interspeech 2023 (CORE A). Bản mở rộng: "Explicit estimation of magnitude and phase spectra in parallel for high-quality speech enhancement", Neural Networks, 2025.*
- **Phương pháp:** cùng encoder và backbone TF-Conformer, với **hai decoder song song**: decoder mask biên độ (sigmoid học được, β = 2) và **decoder pha** dự đoán phần thực/ảo giả rồi lấy `atan2`, nên pha được ước lượng *tường minh*. Loss: magnitude MSE, **loss pha anti-wrapping** (pha tức thời, group delay, tần số góc tức thời), complex MSE, time L1, STFT consistency và loss metric discriminator.
- **Kết quả:** PESQ 3.50, CSIG 4.73, CBAK 3.95, COVL 4.22, STOI 0.96, khoảng 2.05 M tham số.
- **+** State of the art trong các mô hình ~2 M tham số; là mô hình đầu tiên ước lượng pha trực tiếp với loss hiểu hiện tượng quấn pha; có mã nguồn và checkpoint chính thức.
- **−** Sáu thành phần loss với trọng số chọn tay; không causal và có attention bậc hai; chỉ học từ các loại nhiễu của VB-D; huấn luyện theo PESQ có thể overfit metric.

### P3. SGMSE+: Speech Enhancement and Dereverberation with Diffusion-based Generative Models
*J. Richter, S. Welker, J.-M. Lemercier, B. Lay, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023 (Q1).*
- **Phương pháp:** mô hình diffusion dựa trên score trong miền STFT phức. Một phương trình vi phân ngẫu nhiên (SDE) trôi từ tiếng nói sạch về phía hỗn hợp nhiễu, và bộ lấy mẫu predictor–corrector chạy ngược nó, có điều kiện theo đầu vào nhiễu. Backbone là NCSN++.
- **Kết quả:** PESQ 2.93, ESTOI 0.87, SI-SDR 17.3 dB trên VB-D; hoạt động tốt hơn trên tập test lệch miền (huấn luyện trên WSJ0-CHiME3, test trên VB-D).
- **+** Tổng quát hóa tốt và nghe tự nhiên; cùng mô hình còn khử được vang.
- **−** Khoảng 60 lần chạy mạng mỗi câu với mạng khoảng 65 M tham số nên chậm; có thể sinh tiếng thở hoặc âm vị giả ở SNR thấp; PESQ thấp hơn các mô hình discriminative tốt nhất.

### P4. StoRM: A Diffusion-based Stochastic Regeneration Model
*J.-M. Lemercier, J. Richter, S. Welker, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023 (Q1).*
- **Phương pháp:** một mô hình dự đoán (discriminative) cho ước lượng ban đầu, sau đó một mô hình diffusion *tái sinh* các chi tiết từ ước lượng đó. Cách này kết hợp ưu điểm của hai nhóm.
- **+** Loại bỏ lỗi phát âm/tiếng thở giả của diffusion thuần và cần ít bước lấy mẫu hơn nhiều so với SGMSE+.
- **−** Phải huấn luyện và chạy hai mạng; vẫn chậm hơn một mô hình dự đoán đơn lẻ.

### P5. DOSE: Diffusion Dropout with Adaptive Prior for Speech Enhancement
*W. Tai, Y. Lei, F. Zhou, G. Trajcevski, T. Zhong. NeurIPS 2023 (CORE A\*).*
- **Phương pháp:** khắc phục điều kiện yếu trong diffusion SE có điều kiện. *Diffusion dropout* khi huấn luyện buộc mô hình dựa vào điều kiện nhiễu, và *prior thích nghi* bắt đầu lấy mẫu từ một ước lượng nhiễu thay vì nhiễu thuần. Chỉ cần hai bước lấy mẫu.
- **+** Diffusion SE hiệu quả, tổng quát hóa tốt và có phân tích lý thuyết.
- **−** PESQ trên VB-D vẫn thấp hơn nhiều so với SOTA discriminative; phương pháp khó tinh chỉnh.

### P6. GenSE: Generative Speech Enhancement via Language Models using Hierarchical Modeling
*J. Yao, H. Liu, C. Chen, Y. Hu, E. S. Chng, L. Xie. ICLR 2025 (CORE A\*).*
- **Phương pháp:** SE như language modelling có điều kiện. Token ngữ nghĩa từ một mô hình self-supervised và token âm học từ một codec một bộ lượng tử được dự đoán qua hai giai đoạn phân cấp (ngữ nghĩa nhiễu→sạch, rồi ngữ nghĩa→âm học), với token-chain prompting để giữ âm sắc người nói.
- **+** DNSMOS và độ giống người nói cao trên bản ghi thực; bền vững với nhiều loại méo.
- **−** Mô hình lớn và giải mã autoregressive chậm; chủ yếu báo cáo bằng metric non-intrusive kiểu DNS; nguy cơ lệch nội dung hoặc giọng.

### Các công trình liên quan khác
- **MetricGAN+** (Fu et al., Interspeech 2021): mask BLSTM với discriminator học PESQ, PESQ 3.15. Đây là nguồn gốc của metric discriminator dùng trong P1/P2.
- **DeepFilterNet** (Schröter et al., ICASSP 2022; các bản v2/v3): hệ số theo dải ERB cộng *deep filtering* cho SE full-band (48 kHz) thời gian thực với độ phức tạp rất thấp; khoảng 3.1 PESQ trên VB-D với v2/v3.
- **SEMamba** (Chao et al., IEEE SLT 2024): thay Conformer của MP-SENet bằng khối Mamba (state-space), cho mô hình chuỗi thời gian tuyến tính; PESQ 3.55, hoặc 3.69 với perceptual contrast stretching (PCS). Đây là động lực cho cải tiến **PCS** mà chúng tôi đề xuất.

## 3. Bảng tổng hợp (VB-D, theo công bố)

| Mô hình | Nơi công bố | Loại | PESQ | CSIG | CBAK | COVL | STOI | Tham số |
|---|---|---|---|---|---|---|---|---|
| Đầu vào nhiễu | – | – | 1.97 | 3.35 | 2.44 | 2.63 | 0.91 | – |
| MetricGAN+ | Interspeech'21 | Disc. mask | 3.15 | 4.14 | 3.16 | 3.64 | – | – |
| SGMSE+ | TASLP'23 | Diffusion | 2.93 | – | – | – | ESTOI 0.87 | ~65 M |
| CMGAN | TASLP'24 | Disc. biên độ+phức | 3.41 | 4.63 | 3.94 | 4.12 | 0.96 | 1.83 M |
| MP-SENet | Interspeech'23 | Disc. biên độ+pha | 3.50 | 4.73 | 3.95 | 4.22 | 0.96 | 2.05 M |
| SEMamba (+PCS) | SLT'24 | Disc. (Mamba) | 3.55 (3.69) | – | – | – | – | ~2 M |
