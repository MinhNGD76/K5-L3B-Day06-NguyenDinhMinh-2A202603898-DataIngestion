# Benchmark — The Brothers Karamazov

File câu hỏi: [questions.json](questions.json). Chốt ngày 2026-11-14, **trước khi chạy bất kỳ truy xuất nào**.

Kiểm chứng (chạy từ `starter/`): `python -m scripts.verify_benchmark`

Script này kiểm tra:

- mỗi `evidence_quote` (kể cả `alt_evidence`) có nguyên văn trong chương gold sau khi chuẩn hóa;
- `gold_unit_id` khớp với `gold_page`;
- chương gold thỏa giá trị `filter`;
- đủ số câu dev/test và số câu có filter;
- chương gold của test không trùng với chương nào của dev.

## Thành phần

| | Dev | Test |
|---|---:|---:|
| Tổng | 15 | 5 |
| direct / paraphrase / condition | 6 / 4 / 2 | 2 / 1 / 0 |
| filter (`book`) | 3 | 2 |

`gold_page` là số thứ tự chương (1–96) trong [data/manifest.json](../data/manifest.json), không phải trang vật lý. Hit được tính khi chunk thuộc chương gold **và** chứa đủ `evidence_quote` (hoặc một `alt_evidence`).

## Cách chia dev/test

- Test gồm 5 câu từ 5 chương **không xuất hiện trong dev**: BII-CIII, BX-CI, BXII-CI, EP-CI, EP-CIII.
- Có 2 câu filter trong test (Book XII, Epilogue).
- Corpus chỉ có một tài liệu, nên chia theo chương thay vì theo tài liệu.

**Nguy cơ rò rỉ:**

- d08/d14 (dev) và t04 (test) đều liên quan tới chày đồng (brass pestle), nhưng thuộc các chương và book khác nhau.
- Tác giả đã đọc đoạn văn khi soạn câu hỏi, nên cách diễn đạt có thể gần với nguồn hơn câu hỏi của người dùng thật.

## Câu có filter

Filter là **input giả định**: người dùng cho biết họ đang hỏi về book nào **trước khi truy xuất**. Giá trị lấy nguyên văn từ heading của nguồn (Book I–XII, Epilogue).

Các câu này được chọn vì cùng một chủ đề xuất hiện ở nhiều book:

| Câu | Filter | Chủ đề | Vì sao cần filter |
|---|---|---|---|
| d13 | Book III | Dòng chữ trên phong bì | Book V (BV-CVI) có một cách ghi khác |
| d14 | Book IX | Chày đồng | Còn được nhắc ở Book VIII và XII |
| d15 | Book III | Động kinh của Smerdyakov | Còn được nhắc ở Book V, IX và XII |
| t04 | Book XII | Vật chứng | Chày đồng xuất hiện ở nhiều book |
| t05 | Epilogue | Bản án | — |

Với câu không có filter, cấu hình C chạy **không lọc**.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)

Chọn trên **dev** theo thứ tự ưu tiên:

1. Evidence Hit@3 cao hơn.
2. Nếu bằng nhau thì xét Hit@1.
3. Nếu vẫn bằng nhau thì chọn cấu hình có ít chunk/token hơn (tài nguyên).

Grounding và coherence được chấm thủ công trên test **sau khi** đã cố định lựa chọn; chúng dùng để phân tích, không dùng để chọn lại. Test chỉ chạy một lần sau khi chốt cấu hình.

## Ghi chú trung thực

Câu hỏi được soạn với hỗ trợ của AI (Claude Code): tìm đoạn văn trong corpus, đề xuất câu hỏi và evidence nguyên văn. Học viên rà soát lại câu hỏi và đáp án. Evidence được kiểm chứng tự động bằng script nói trên.
