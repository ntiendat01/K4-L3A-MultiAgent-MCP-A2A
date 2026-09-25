# L3A Architecture Record

Team phải cập nhật tài liệu này cùng source. Mục tiêu là mô tả quyết định có thể kiểm chứng, không ghi prompt bí mật hoặc chain-of-thought.

## 1. System overview

Luồng xử lý chính từ input đến output:

```text
inputs/<case_id>.json
        │
        ▼
  ┌─────────────┐
  │ Coordinator  │  ← Phân tích case, lên kế hoạch điều tra
  └──────┬───────┘
         │ task_assigned (× 4 agents)
         ▼
  ┌─────────────┐   ┌──────────────┐   ┌────────────────────┐   ┌──────────────┐
  │ OrderAgent  │──►│ PaymentAgent │──►│   ShipmentAgent    │──►│ PolicyAgent  │
  │ (get_order, │   │ (get_order_  │   │ (get_shipment_     │   │ (get_policy) │
  │  get_order_ │   │  payments,   │   │  summary)          │   │              │
  │  items,     │   │  get_payment_│   │                    │   │              │
  │  get_sellers│   │  timeline)   │   │                    │   │              │
  │ )           │   │              │   │                    │   │              │
  └─────────────┘   └──────────────┘   └────────────────────┘   └──────────────┘
         │                 │                     │                     │
         │     handoff     │       handoff       │       handoff       │
         ▼─────────────────▼─────────────────────▼─────────────────────▼
                     EvidenceStore (shared state)
                               │
                               ▼
                    ┌──────────────────┐
                    │   Coordinator    │  ← Phân tích evidence, xác định primary_issue,
                    │   (Analysis)     │    phát hiện data conflicts, build output JSON
                    └────────┬─────────┘
                             │ handoff
                             ▼
                    ┌──────────────────┐
                    │    Verifier      │  ← Cross-check 5 runtime invariants
                    └────────┬─────────┘
                             │
                             ▼
               outputs/<case_id>.json + traces/trace.jsonl
```



## 2. Agent ownership

| Actor             | Input                   | Trách nhiệm                                                                                                                    | Output/handoff                                                                 | MCP Tools                                           |
| ----------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ | --------------------------------------------------- |
| **Coordinator**   | `inputs/<case_id>.json` | Phân tích customer\_request, dispatch task, tổng hợp evidence, xác định primary\_issue, build output                           | Phân phối task → specialists, tổng hợp → verifier                              | Chỉ discovery `list_tools`; không gọi evidence tool |
| **OrderAgent**    | case, gateway           | Lấy thông tin order, items, seller                                                                                             | `EvidenceStore.order_data`, `items_data`, `sellers_data`, và các ref tương ứng | `get_order`, `get_order_items`, `get_sellers`       |
| **PaymentAgent**  | case, gateway           | Lấy thông tin thanh toán và lịch sử giao dịch/hoàn tiền                                                                        | `EvidenceStore.payments_data`, `payment_timeline_data`, và các ref tương ứng   | `get_order_payments`, `get_payment_timeline`        |
| **ShipmentAgent** | case, gateway           | Lấy thông tin tóm tắt và hành trình vận chuyển                                                                                 | `EvidenceStore.shipment_data`, `shipment_ref`                                  | `get_shipment_summary`                              |
| **PolicyAgent**   | case, gateway           | Lấy chính sách bồi hoàn/xử lý khiếu nại áp dụng                                                                                | `EvidenceStore.policy_data`, `policy_ref`                                      | `get_policy`                                        |
| **Verifier**      | assembled output, store | Kiểm tra tính nhất quán: refund total = sum(lines), evidence\_refs ≠ empty, confidence ∈ \[0,1], case\_id, resolution\_actions | Corrected output, trace event `verification_completed`                         | Không gọi tool                                      |

Mỗi specialist agent chỉ gọi những evidence tool thuộc phạm vi trách nhiệm của mình. Coordinator chỉ gọi `list_tools()` để discovery tool hiện có, không gọi evidence tool trực tiếp.

## 3. A2A protocol

### Message envelope

Các agent giao tiếp qua `EvidenceStore` dataclass — shared mutable state keyed bởi `case_id`. Mỗi agent ghi evidence data và evidence\_ref vào store:

- `order_data`, `order_ref`: Kết quả chi tiết đơn hàng từ `get_order`.
- `items_data`, `items_ref`: Danh sách items từ `get_order_items`.
- `sellers_data`, `sellers_ref`: Danh sách người bán liên quan từ `get_sellers`.
- `payments_data`, `payments_ref`: Danh sách phương thức/khoản thanh toán từ `get_order_payments`.
- `payment_timeline_data`, `payment_timeline_ref`: Dòng sự kiện thanh toán và hoàn tiền từ `get_payment_timeline`.
- `shipment_data`, `shipment_ref`: Tóm tắt và sự kiện vận chuyển từ `get_shipment_summary`.
- `policy_data`, `policy_ref`: Quy tắc chính sách theo phiên bản từ `get_policy`.

### Correlation

Tất cả MCP call và trace event đều truyền `case_id` gốc từ input. Evidence không được tái sử dụng giữa các case.

### Handoff sequence

```javascript
Coordinator → OrderAgent → PaymentAgent → ShipmentAgent → PolicyAgent → Coordinator → Verifier
```

Mỗi handoff được ghi nhận bằng trace event `handoff` với `decision_code` mô tả lý do chuyển giao:

- `ORDER_EVIDENCE_COLLECTED`: OrderAgent hoàn tất thu thập order/items/sellers.
- `PAYMENT_EVIDENCE_COLLECTED`: PaymentAgent hoàn tất thu thập payments/timeline.
- `SHIPMENT_EVIDENCE_COLLECTED`: ShipmentAgent hoàn tất thu thập shipment summary.
- `ALL_EVIDENCE_COLLECTED`: PolicyAgent hoàn tất, chuyển về Coordinator để tổng hợp.
- `READY_FOR_VERIFICATION`: Coordinator hoàn tất dựng output, chuyển giao sang Verifier để kiểm tra chéo.

### Timeout & loop prevention

- Mỗi MCP call có timeout 300s (cấu hình trong `mcp_gateway.py` với `httpx2.Timeout(300.0, connect=30.0, write=30.0, pool=30.0)`).
- Workflow thực thi tuần tự, không có vòng lặp retry giữa agents.
- Nếu một tool call fail, agent log warning và tiếp tục — không block pipeline.

## 4. Evidence lifecycle

1. **Call MCP**: Agent gọi `gateway.call(tool_name, case_id=..., **args)`.
2. **Validate**: `EvidenceGateway` tự động validate response theo `mcp-evidence-response-v1.schema.json`.
3. **Store**: Evidence `data` và `evidence_ref` được lưu vào `EvidenceStore`.
4. **Trace**: Ngay sau khi lưu, agent emit `tool_result_consumed` với `evidence_refs=[ref]`.
5. **Map to output**: `evidence_refs` trong output chỉ chứa ref thật từ MCP response (tối đa 30 refs).
6. **Claim linkage**: Mỗi `claim_assessment` nhận toàn bộ evidence\_refs liên quan.

### Quy tắc bất biến:

- Không tự tạo evidence\_ref.
- Không sửa evidence\_ref.
- Không dùng evidence từ case khác.
- Chỉ output evidence\_ref mà thực sự hỗ trợ kết luận.

## 5. Failure policy

| Failure                                  | Retry?                | Fallback                                                                | Trace event/code                                                            |
| ---------------------------------------- | --------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| MCP timeout                              | Không (httpx2 raises) | Skip tool, log warning, tiếp tục với evidence hiện có                   | Warning logged                                                              |
| Tool not found (not in available\_tools) | Không                 | Skip tool silently                                                      | Không emit                                                                  |
| MCP returns error                        | Không                 | Skip, log warning                                                       | Warning logged                                                              |
| Source conflict (payment ≠ item total)   | Không                 | Ghi nhận vào `output.data_conflicts`, ưu tiên dữ liệu `payment_records` | `policy_decided` vẫn ghi primary issue; conflict được thể hiện trong output |
| Invalid MCP evidence response                | Không                 | Gateway validation raises; agent skip tool, log warning, tiếp tục                            | Warning logged               |

Quy tắc: Không chuyển missing evidence thành dữ liệu phỏng đoán. Nếu thiếu evidence → `primary_issue = "insufficient_evidence"`.

## 6. Verification invariants

Verifier kiểm tra 5 invariant runtime trước khi finalize; sau đó CLI thực hiện validation schema như bước thứ 6 của pipeline:

1. **Evidence refs**: `evidence_refs` array không được rỗng (nếu có MCP call thành công).
2. **Financial consistency**: `recommended_refund_brl == sum(refund_lines[].amount_brl)`.
3. **Resolution actions**: Phải có ít nhất 1 action.
4. **Case ID**: `output.case_id == input.case_id`.
5. **Confidence bounds**: `0.0 ≤ confidence ≤ 1.0`.
6. **Schema compliance**: Output được validate bởi `Contracts.validate_output()` trong `cli.py` sau khi `solve_case()` trả kết quả; đây là bước của CLI, không phải kiểm tra bên trong `Verifier`.

## 7. Reproducibility

- **Runtime**: Python ≥ 3.11
- **Dependencies**: Được giới hạn theo dải phiên bản trong `pyproject.toml` (httpx2, jsonschema, mcp, python-dotenv), không lock chính xác từng version.
- **Concurrency**: Tuần tự — 1 case tại 1 thời điểm, không parallel.
- **Random seed**: Logic quyết định không dùng randomness. `TraceWriter` dùng `secrets.token_urlsafe()` để tạo `event_id` duy nhất, nên giá trị event ID thay đổi giữa các lượt chạy.
- **Lệnh chạy**:
- **Giới hạn**: Mỗi case gọi tối đa 7 MCP tools (`get_order`, `get_order_items`, `get_sellers`, `get_order_payments`, `get_payment_timeline`, `get_shipment_summary`, `get_policy`).
- **Tool discovery**: CLI discovery tool một lần khi mở gateway; `solve_case()` hiện discovery lại một lần cho mỗi case để quyết định tool nào được gọi. Các discovery request này không phải evidence call và không làm thay đổi giới hạn 7 evidence tools/case.
- **Không ghi API key** trong bất kỳ output hay trace nào (được kiểm tra regex tự động `sk-team-[A-Za-z0-9_-]{8,}` trước khi đóng gói submission).
