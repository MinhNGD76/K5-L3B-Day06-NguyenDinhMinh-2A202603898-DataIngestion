# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - Tiểu thuyết *The Brothers Karamazov* (Dostoyevsky, bản dịch Constance Garnett), Project Gutenberg eBook #28054, file `starter/data/The Brothers Karamazov.txt` (UTF-8, tải ngày 2026-11-14). Public domain tại Mỹ theo Project Gutenberg; file giữ nguyên license đi kèm. Chi tiết trong [data/manifest.json](../../data/manifest.json), gồm SHA-256 của file.
  - Văn bản không có trang vật lý, nên theo GUIDE mỗi **chương là một đơn vị nguồn độc lập**; `page` = số thứ tự chương 1–96. **96 chương, 1.925.924 ký tự chuẩn hóa**, mỗi chương từ 7.233 đến 50.188 ký tự (ngưỡng yêu cầu: 1.500 ký tự/đơn vị, tối thiểu 30 đơn vị).
  - Loại khỏi corpus: header/license Gutenberg, trang tựa, mục lục, phần FOOTNOTES của người dịch, và các dòng heading (heading được giữ làm metadata).
- **Chuẩn hóa, lỗi và giới hạn:**
  - Chuẩn hóa Unicode NFC, đổi CRLF thành LF, nối các dòng bị ngắt cứng thành một đoạn, giữ dòng trống giữa các đoạn ([ingestion.py](../../starter/src/ingestion.py)).
  - Không có chương rỗng hay lỗi đọc (kiểm tra trong [build_manifest.py](../../starter/scripts/build_manifest.py): 96 chương khớp 96 mục trong mục lục, `unit_id` không trùng).
  - Giới hạn: đơn vị truy vết là chương, trung bình khoảng 20.000 ký tự, **thô hơn nhiều so với trang**; "đúng chương" chưa nói lên nhiều, nên Hit được tính ở mức chunk (xem định nghĩa bên dưới). Đây là bản dịch tiếng Anh nên không kiểm tra được khả năng đa ngữ.
- **Embedding, vector store, metric, lệnh chạy và chi phí:**
  - Embedding: OpenRouter, provider OpenAI, model `openai/text-embedding-3-small`, **1536 chiều**. Model đối xứng: query và document được embed như nhau, không thêm prefix. Dùng `urllib`, không cài thêm SDK ([embeddings.py](../../starter/src/embeddings.py)); lỗi API thì dừng, không dùng vector giả.
  - Vector store: PostgreSQL 16.16 + pgvector 0.8.7 (image `pgvector/pgvector:0.8.7-pg16`, Docker Compose), **cosine, tìm kiếm chính xác** (không có index ANN). `psycopg[binary]==3.3.8`, Python 3.11.
  - Lệnh (từ `starter/`): `docker compose -p day6_student_starter up -d --wait`, `python -m src.run ingest` (chạy 2 lần), `python -m src.run eval dev`, `python -m src.run eval test` (một lần). Test offline: `python -m tests.test_pipeline`. Kiểm chứng benchmark: `python -m scripts.verify_benchmark`.
  - Chi phí thực từ API: nạp A $0,010243 (512.128 token), nạp B $0,009168 (458.387 token); C dùng lại index B nên không tốn thêm. Embed câu hỏi: $0,000005 (dev) + $0,000001 (test). Tổng hai lần nạp và hai lần đánh giá khoảng **$0,039**.
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - Bắt buộc: `document_id`, `source`, `page` (số thứ tự chương). Có thêm `unit_id`, `chapter`, `chapter_title`, `part`, `book` và vị trí ký tự `char_start`/`char_end` trong chương.
  - Trường lọc: **`book`** (Book I–XII và Epilogue, 13 giá trị) và `part` (5 giá trị). Giá trị lấy nguyên văn từ heading "Book N. Title" và "PART N" trong nguồn, không tự đặt.
  - Lý do chọn `book`: các chủ đề lặp lại ở nhiều book (phong bì tiền, chày đồng, động kinh của Smerdyakov), nên lọc theo book giúp giới hạn phạm vi. Hạn chế: filter là **input giả định**, người dùng phải biết trước mình đang hỏi về book nào; book có độ dài rất khác nhau nên mức "thu hẹp" của filter không đồng đều.

## Cấu hình và benchmark

- **A / B / C:**

| Cấu hình | Chunk | Metadata / truy xuất |
|---|---|---|
| A | Cửa sổ cố định 500 ký tự, overlap 50, trong phạm vi một chương | Gắn nguồn/chương/book; không lọc |
| B | Gom nguyên các đoạn văn đến tối đa 500 ký tự; đoạn dài hơn thì cắt theo câu, câu dài hơn nữa thì cắt cứng | Giống A; không lọc |
| C | **Cùng index với B** | Thêm lọc `book` trong SQL, chỉ áp dụng cho câu có filter (d13, d14, d15, t04, t05); các câu còn lại chạy không lọc |

  - Khác biệt duy nhất **B–C là bộ lọc** (cùng index, cùng truy vấn). A–B thay cách cắt chunk với cùng mức 500 ký tự, nhưng A có overlap 50 còn B không, nên A–B khác nhau ở hai yếu tố liên quan: ranh giới chunk và overlap.
  - Số chunk: A **4.318**, B/C **4.659**. Độ dài chunk (min / trung vị / trung bình / max): A 50 / 500 / 494,5 / 500; B 43 / 437 / 412,0 / 500.
- **≥20 câu, phân chia, filter và kiểm chứng evidence:**
  - **20 câu: 15 dev, 5 test** ([benchmark/questions.json](../../benchmark/questions.json)): 8 trực tiếp, 5 diễn đạt lại, 2 điều kiện, 5 có filter (3 dev: d13, d14, d15; 2 test: t04, t05).
  - 5 câu test lấy từ 5 chương không xuất hiện trong dev. Chủ đề chày đồng vẫn có ở cả dev (d08, d14) và test (t04), ở các chương khác nhau; đã ghi như một nguy cơ rò rỉ trong [benchmark/README.md](../../benchmark/README.md).
  - Mỗi câu có `evidence_quote` nguyên văn. `python -m scripts.verify_benchmark` kiểm tra quote nằm trong chương gold sau chuẩn hóa, chương gold thỏa filter, đủ số câu dev/test/filter và test không chung chương với dev. Script cũng đã được thử trên bản sao cố tình làm hỏng và bắt được cả 5 loại lỗi cài vào.
  - Câu hỏi được soạn với hỗ trợ của AI (xem phần AI bên dưới); tôi rà soát lại.
- **Tiêu chí chọn chiến lược chốt trước khi xem test:** trên **dev**: Evidence Hit@3 cao hơn, nếu bằng nhau thì Hit@1, nếu vẫn bằng nhau thì ít chunk/token hơn. Ghi trong [benchmark/README.md](../../benchmark/README.md) và [experiment_log.csv](../../artifacts/experiment_log.csv). **Lưu ý trung thực:** thời điểm viết báo cáo, các file này chưa được commit vào git, nên chưa có mốc thời gian git độc lập cho việc "chốt trước khi chạy".

## Kết quả

Hit = chunk thuộc đúng chương gold **và chứa trọn** `evidence_quote` (hoặc một `alt_evidence`). Thời gian là thời gian thực (gồm độ trễ API), lấy lần nạp đầu; lần nạp lại mất A 228,7 giây và B 283,7 giây, nên chênh lệch giữa các lần chạy cỡ 25%.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian nạp | Chi phí nạp |
|---|---|---|---|---|---|---|
| A | dev | 3/15 | 3/15 | 4.318 | 301,9 s | $0,0102 |
| A | test | 1/5 | 3/5 | (như trên) | | |
| B | dev | 5/15 | 7/15 | 4.659 | 319,7 s | $0,0092 |
| B | test | 1/5 | 2/5 | (như trên) | | |
| C | dev | 6/15 | 7/15 | 4.659 (dùng index B) | 0 (dùng lại B) | $0 thêm |
| C | test | 1/5 | 2/5 | (như trên) | | |

Chỉ số chẩn đoán (không thay Hit): `gold_page@3` là số câu có ít nhất một chunk top-3 thuộc đúng chương gold. Dev: A 10/15, B 10/15, C 11/15. Test: A 4/5, B 4/5, C 5/5.

Nạp lại cùng phiên bản không sinh bản trùng: hai lần nạp đều cho `rows_in_db` bằng số chunk (4.318 và 4.659), `duplicates_or_stale = 0` ([results/ingest_log.jsonl](../../results/ingest_log.jsonl)). Khi nguồn đổi, chunk cũ của cùng tài liệu bị xóa trong cùng transaction; điều này đã kiểm bằng smoke test trên chiến lược tạm `smoke` (đã xóa), chưa chạy lại trên dữ liệu thật.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0.4 | 15/15 (kiểm tra tự động, xem dưới) | test 1/2 (dev 0/3) | 0.5 |
| B | 0.6 | 15/15 (kiểm tra tự động, xem dưới) | test 1/2 (dev 0/3) | 0.7 |
| C | 0.6 | 15/15 (kiểm tra tự động, xem dưới) | test 2/2 (dev 3/3) | 0.7 |

Cột filter là kết quả tự động: số câu có filter mà toàn bộ top-3 thuộc đúng book yêu cầu. Với A và B, bộ lọc **không được áp dụng**; con số cho biết top-3 có tình cờ nằm đúng book hay không.

- **Trace:** [results/traces_dev.jsonl](../../results/traces_dev.jsonl) và [results/traces_test.jsonl](../../results/traces_test.jsonl) (top-3 đầy đủ: chunk ID, text, score, book, cờ hit). Số liệu tổng hợp: [results/metrics_dev.json](../../results/metrics_dev.json), [results/metrics_test.json](../../results/metrics_test.json).
- **Cách chọn mẫu (cố định trước khi chấm, seed 20261114):** [starter/scripts/prepare_manual_audit.py](../../starter/scripts/prepare_manual_audit.py) tạo phiếu chấm trong [results/manual/](../../results/manual/).
  - **Coherence:** 10 vị trí = điểm giữa của các chương 5, 15, 25, …, 95 (rải đều khắp tiểu thuyết). Với mỗi vị trí lấy chunk chứa nó trong A và B; **C dùng cùng chunk với B** nên dùng lại nhãn của B. Tổng 20 chunk, thứ tự xáo và ẩn tên chiến lược.
  - **Grounding:** 5 câu test × top-3 của A, B, C; khi B và C lấy cùng top-3 thì chấm một lần cho cả hai (11 ca, tương ứng 15 kết quả). Phiếu ẩn tên chiến lược.
  - **Metadata:** 5 câu test × top-3 × 3 chiến lược = 45 bản ghi (15 mỗi chiến lược). Kiểm tra tự động: các trường `document_id`, `source`, `page`, `book`, `part` có đủ, khớp manifest và dòng trong DB, và text chunk nằm trong đúng chương ([metadata_check.csv](../../results/manual/metadata_check.csv)). Vì metadata và manifest do cùng một bộ đọc tạo ra nên kiểm tra này **có tính vòng tròn**; để độc lập hơn, mình còn tìm từng chunk trong **file gốc** và so heading Book/Chapter gần nhất phía trên với metadata: **45/45 khớp**. Đây là đối chiếu máy; tác giả cần rà soát lại.
  - Người chấm coherence và grounding là tác giả, có nguy cơ thiên lệch vì chính tác giả đã soạn câu hỏi; chấm sau khi đã xem kết quả truy xuất nên chưa thật độc lập.
  - Hạn chế của metadata: kiểm tra chỉ xác nhận trường đúng với nguồn, không chứng minh hữu ích. `book` giúp lọc và truy vết (đã thấy ở C), nhưng `page` là số thứ tự chương nên chỉ truy được tới cả chương (khoảng 20.000 ký tự), không tới đúng đoạn; `char_start`/`char_end` đã lưu trong metadata để bù phần này.

## Phân tích và kết luận

- **Quy trình test:** tôi xác nhận đã chạy `eval test` **đúng một lần**, sau khi chọn C trên dev. Giới hạn: `metrics_test.json` chỉ ghi một thời điểm (2026-11-14 04:17:53 UTC) và bị ghi đè nếu chạy lại, nên file không tự chứng minh điều này.
- **A–B (cách cắt chunk):**
  - Dev: Hit@1 3/15 lên 5/15, Hit@3 3/15 lên 7/15, trong khi `gold_page@3` giữ nguyên 10/15 cho cả hai. Nghĩa là B không tìm đúng chương nhiều hơn, mà **cùng một chương nhưng chunk của B chứa trọn evidence thường xuyên hơn**.
  - **Test không ủng hộ điều đó:** Hit@3 A 3/5 so với B 2/5. Cụ thể A đúng ở t01 và t04 mà B trượt, B đúng ở t03 mà A trượt. Với 5 câu, chênh một câu bằng 20 điểm phần trăm và **không đủ để kết luận** chiều nào hơn.
  - Tài nguyên: A tốn nhiều token hơn khoảng 11,7% (512.128 so với 458.387) do overlap, với số chunk ít hơn B (4.318 so với 4.659).
- **B–C (bộ lọc `book`):**
  - Hit@3 không đổi (dev 7/15, test 2/5). Hit@1 dev tăng 5/15 lên 6/15 (d13: từ hạng 3 lên hạng 1). `gold_page@3` tăng 10/15 lên 11/15 ở dev (d15) và 4/5 lên 5/5 ở test (t05). Tuân thủ filter lên 3/3 ở dev và 2/2 ở test.
  - Kết luận: filter **đảm bảo top-3 nằm đúng book**, nhưng không biến top-3 thành chunk chứa trọn evidence. Giả thuyết ban đầu "filter tăng Hit@1/Hit@3 trên 5 câu filter" chỉ đúng một phần: chỉ Hit@1 dev tăng 1 câu.
- **Hai ví dụ sai:**
  1. **d15** (dev, filter Book III), nguồn Book III, Chương VI (`BIII-CVI`, trang 19). Cấu hình C lọc đúng book và top-3 có 2 chunk của đúng chương, nhưng vẫn trượt. Evidence gồm hai câu liền nhau ("The boy took the slap … A week later he had his first attack of the disease … epilepsy"). Chunk top-2 bắt đầu bằng "A week later he had his first attack…", tức nửa đầu của trích dẫn nằm ở chunk khác. Đây là lỗi **evidence bị tách qua nhiều chunk**, một hệ quả của định nghĩa Hit nghiêm ngặt (cần trọn evidence trong một chunk). Ở B không lọc, top-3 rơi vào Book V, IX và XII, tức đúng kiểu nhiễu mà filter dự kiến loại bỏ.
  2. **d06** (dev, không filter), nguồn Book VI, Chương II (`BVI-CII`, trang 40): "What did Zossima do with his pistol after his opponent fired at him in the duel?". Cả A, B và C đều trượt và top-3 **không có chunk nào của đúng chương** (`gold_page@3` không đạt). Top-3 của B là chunk nói về khẩu súng của Mitya ở Book VIII và XII và một chunk ở Book IV. Embedding bắt từ khóa chủ đề "pistol" nhưng không phân biệt nhân vật và bối cảnh (Zossima, duel). Câu không có filter nên C không giúp được.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - Chọn **C**. Trên dev B và C bằng nhau về Hit@3 (7/15), C hơn về Hit@1 (6/15 so với 5/15), A kém hơn cả hai. Tiêu chí được áp dụng đúng như đã chốt, nhưng **lợi thế của C so với B trên dev chỉ là một câu** và trên test C bằng B. Trên test, A có Hit@3 cao nhất (3/5); tôi **không đổi lựa chọn** sau khi xem test, theo quy tắc đã đặt.
  - Đánh đổi: C chỉ có ích khi người dùng cung cấp được book trước khi hỏi, và không tốn thêm chi phí nạp. Nếu không có filter thì C hoạt động như B.
  - Điều kiện áp dụng: kết luận chỉ có giá trị cho **một cuốn tiểu thuyết tiếng Anh, một embedding model, chunk ~500 ký tự**.
- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - Test chỉ có 5 câu (2 câu filter): một câu đổi kết quả 20 điểm phần trăm, nên mọi chênh lệch A/B/C trên test nằm trong sai số mẫu. Dev 15 câu cũng nhỏ.
  - Hit nghiêm ngặt (cần trọn quote trong một chunk) phạt cả hai chiến lược khi evidence dài hơn ranh giới chunk; evidence dài (d15, t04) bị ảnh hưởng nhiều hơn evidence ngắn.
  - Một tài liệu duy nhất, đơn vị chương thô; câu hỏi do tác giả soạn từ chính đoạn văn nên có thể gần nguyên văn hơn câu hỏi người dùng thật.
  - Thời gian đo bằng đồng hồ thực, phụ thuộc mạng/API và dao động giữa các lần chạy; chi phí lấy từ trường `usage.cost` của API.
  - Chưa chấm thủ công: coherence, metadata đủ/đúng, grounding (xem phần trạng thái ở đầu).
- **Nếu làm lại hoặc mở rộng:**
  - Hoàn thành các nhãn thủ công trước khi kết luận về khía cạnh 2, 3 và 4.
  - Thêm đánh giá "hợp bằng chứng đa chunk" để tách lỗi cắt chunk khỏi lỗi truy xuất ngữ nghĩa (d15, t04).
  - Mở rộng test (thêm câu, thêm tài liệu), dùng đơn vị truy vết nhỏ hơn chương, thử hybrid (BM25 + dense) cho các câu thiếu ngữ cảnh như d06.

## Việc dùng AI và cách kiểm tra (theo RULES)

- Claude Code (Anthropic) được dùng để: viết code trong `starter/src/` và `starter/scripts/`, đề xuất và soạn bộ câu hỏi benchmark cùng evidence, và hỗ trợ phân tích kết quả.
- Cách kiểm tra: bộ test offline cho chunking/đánh giá (5 test), smoke test với DB thật (upsert lặp, xóa chunk cũ, filter, từ chối tên trường lọc không hợp lệ), script kiểm chứng benchmark đã thử với dữ liệu cố tình sai, và đối chiếu số trong báo cáo với `results/metrics_*.json`.
- Không dùng LLM làm người chấm nhãn. Không có số liệu hay nhãn nào trong báo cáo được tạo mà chưa chạy.
