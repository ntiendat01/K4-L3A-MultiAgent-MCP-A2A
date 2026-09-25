# L3A Multi-Agent Architecture & Workflow Specification

Tài liệu mô tả chi tiết kiến trúc hệ thống Multi-Agent xử lý điều tra khiếu nại thương mại điện tử (K4-L3A Competition - MCP & Agent-to-Agent Protocol).

---

## 1. Tổng quan hệ thống (System Overview)

Hệ thống hoạt động theo mô hình **Hybrid Multi-Agent Workflow**, tiếp nhận các hồ sơ khiếu nại (`inputs/L3A_CASE_xxx.json`), phối hợp xử lý qua Coordinator Agent và các Specialist Agents kết nối với **MCP Evidence Gateway**, được tổng hợp & kiểm chứng bởi Verifier Agent để xuất file kết quả (`outputs/L3A_CASE_xxx.json`) cùng nhật ký thực thi quan sát được (`traces/trace.jsonl`).

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                 COORDINATOR AGENT                                     │
│  • Receives Case Input (claimed_order_id, claims, policy_version)                     │
│  • Emits: case_received ──► task_assigned ──► handoff (DISPATCH_ALL_SPECIALISTS)      │
└───────────────────────────┬───────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────────────┬───────────────────────┐
            ▼               ▼                       ▼                       ▼
    ┌───────────────┐┌───────────────┐     ┌─────────────────┐     ┌──────────────────┐
    │  Order Agent  ││ Payment Agent │     │ Shipment Agent  │     │   Policy Agent   │
    │ get_order     ││ get_order_pmts│     │ get_shipment_sm │     │ get_policy       │
    │ get_order_itms││ get_pmt_tline │     │ get_sellers     │     │ (Policy Oracle)  │
    │ get_sellers   ││ get_rfnd_tline│     └────────┬────────┘     └────────┬─────────┘
    └───────┬───────┘└───────┬───────┘              │                      │
            │                │                      │                      │
            └────────────────┴───────────┬──────────┴──────────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │      VERIFIER / SYNTHESIZER     │
                        │ • Aggregates Evidence & Policy  │
                        │ • Checks Schema & Invariants    │
                        │ • Emits: verification_completed │
                        │ • Emits: case_finalized         │
                        └────────────────┬────────────────┘
                                         ▼
                            Outputs (L3A_CASE_xxx.json)
```

---

## 2. Phân định trách nhiệm các Agents (Agent Ownership Table)

| Agent Actor | Đầu vào (Inputs) | Trách nhiệm cốt lõi | Công cụ MCP sử dụng (MCP Tools) | Sự kiện Trace phát hành |
|---|---|---|---|---|
| **Coordinator Agent** | Case JSON (`case_id`, `customer_request`) | Tiếp nhận hồ sơ, trích xuất mã đơn hàng (`claimed_order_id`), loại khiếu nại (`claims`), điều phối chuyên viên. | *(Không trực tiếp gọi MCP)* | `case_received`, `task_assigned`, `handoff` |
| **Order Agent** | `case_id`, `claimed_order_id` | Truy vấn thông tin đơn hàng, danh sách sản phẩm, gian hàng bán. | `get_order`<br>`get_order_items`<br>`get_sellers` | `tool_result_consumed` |
| **Payment Agent** | `case_id`, `claimed_order_id` | Truy vấn các đợt thanh toán, mốc thời gian thanh toán, lịch sử xử lý hoàn tiền. | `get_order_payments`<br>`get_payment_timeline`<br>`get_refund_timeline` | `tool_result_consumed` |
| **Shipment Agent** | `case_id`, `claimed_order_id` | Truy vấn thông tin vận chuyển, kiểm tra độ trễ giao hàng và đối tượng chịu trách nhiệm. | `get_shipment_summary` | `tool_result_consumed` |
| **Policy Agent** | `case_id`, `policy_version` | Tra cứu điều khoản chính sách ground-truth (Policy Oracle) cho từng loại vi phạm. | `get_policy` | `tool_result_consumed`, `policy_decided` |
| **Verifier Agent** | Kết quả tổng hợp từ tất cả Specialists | Kiểm tra JSON Schema compliance, tính nhất quán tài chính, đối soát bằng chứng `evidence_ref`. | *(Không trực tiếp gọi MCP)* | `verification_completed`, `case_finalized` |

---

## 3. Giao thức A2A & Trace Standard (Agent-to-Agent Protocol)

1. **Correlation Envelope**: `case_id` được sử dụng làm khóa tương quan duy nhất truyền qua tất cả các agent và trace log.
2. **Lifecycle Event Chain**:
   - `case_received`: Coordinator bắt đầu nhận hồ sơ.
   - `task_assigned`: Phân công nhiệm vụ cụ thể cho từng Specialist (`order-agent`, `payment-agent`, `shipment-agent`, `policy-agent`).
   - `handoff`: Phát chuyển nhiệm vụ với `decision_code="DISPATCH_ALL_SPECIALISTS"`.
   - `tool_result_consumed`: Ghi nhận dữ liệu bằng chứng thu thập thành công từ MCP.
   - `policy_decided`: Ghi nhận quyết định chính sách xử lý của Policy Agent.
   - `verification_completed`: Verifier hoàn tất kiểm tra Schema & Logic.
   - `case_finalized`: Kết thúc xử lý case.
3. **Trace Privacy Boundary**: Không ghi chép chuỗi suy luận riêng tư (Chain-of-Thought) hay prompt thô vào trace log công khai.

---

## 4. Chiến lược xử lý & Vòng đời bằng chứng (Hybrid Reasoning & Evidence Lifecycle)

### 4.1. Hybrid Reasoning Alignment (Cân bằng Ngữ nghĩa & Bằng chứng)
- **Policy Oracle Ground-Truth**: Sử dụng dữ liệu quy chuẩn từ `get_policy` (`refund_brl`, `case_status`, `recommended_action`, `responsible_parties`) để đảm bảo điểm ngữ nghĩa chính xác tuyệt đối (Semantic Accuracy).
- **Multi-Source Evidence Extraction**: Đồng thời thu thập các thực thể (`order_ids`, `item_ids`, `seller_ids`, `payment_references`, `shipment_ids`) từ toàn bộ các công cụ MCP để phục vụ đối soát bằng chứng (Evidence Coverage & Provenance).

### 4.2. Evidence Lifecycle
1. **MCP Discovery & Execution**: Gọi MCP Gateway qua `EvidenceGateway.call(tool_name, case_id=..., ...)`.
2. **Strict Schema Validation**: Tự động xác thực payload phản hồi theo `mcp-evidence-response-v1.schema.json`.
3. **Provenance Tracking**: Trích xuất chuỗi `evidence_ref` (dạng `ev_...`) duy nhất gắn kết vào `claim_assessments` và mảng root `evidence_refs`.
4. **Isolating Evidence Scopes**: Đảm bảo không sử dụng lại `evidence_ref` giữa các case khác nhau.

---

## 5. Cơ chế xử lý lỗi & Độ ổn định kết nối (Resilience & Connection Recovery)

| Loại sự cố | Giải pháp xử lý (Handling Mechanism) | Mã sự cố / Trạng thái |
|---|---|---|
| **MCP Connection Drop / Timeout** | Vòng lặp Reconnect tự động ở cấp CLI (`cli.py` persistent connection-resume pattern) giúp tiếp tục xử lý mượt mà từ case đang dang dở mà không bị ngắt quãng. | Auto-Resume / Exponential Backoff |
| **Tool Execution Exception** | Bọc khối `try-except` cho các MCP tool mở rộng (`get_shipment_summary`, `get_payment_timeline`, `get_refund_timeline`, `get_sellers`), cho phép luồng tiếp tục chạy nếu tool không có dữ liệu. | Graceful Degrade / Fallback |
| **Unmapped Policy Topic** | Sử dụng cấu hình mặc định an toàn (`status="no_action"`, `refund_brl=0.0`, `action="document_no_action"`). | `unsupported_claim` |

---

## 6. Các điều kiện bất biến (Verification Invariants)

Tất cả kết quả xuất ra `outputs/L3A_CASE_xxx.json` bắt buộc tuân thủ 100%:
1. **JSON Schema Compliance**: Khớp hoàn toàn với schema `day09-l3a-output-v2.schema.json`.
2. **Deterministic Status Consistency**:
   - Nếu `recommended_refund_brl > 0` $\rightarrow$ `case_status = "action_required"`.
   - Nếu `recommended_refund_brl == 0` $\rightarrow$ `case_status` là `"no_action"` hoặc `"needs_investigation"`.
3. **Refund Line Integrity**: Tổng số tiền trong `refund_lines` phải bằng đúng `recommended_refund_brl`.
4. **Evidence Uniqueness & Trace Alignment**: Mọi `evidence_ref` xuất ra file JSON phải tồn tại trong Trace Log của case tương ứng.

---

## 7. Hướng dẫn tái tạo & Vận hành (Reproducibility & Execution Commands)

- **Môi trường**: Python 3.11+ (Virtualenv `.venv`)
- **Phụ thuộc**: `httpx2`, `mcp`, `jsonschema`, `pydantic`

### Các câu lệnh thực thi (CLI Commands):
```bash
# 1. Kiểm tra dữ liệu đầu vào (100 cases)
.venv/bin/python -m student_agent.cli validate-inputs

# 2. Kiểm tra danh sách các công cụ MCP Gateway
.venv/bin/python -m student_agent.cli mcp-tools

# 3. Thực thi Workflow xử lý toàn bộ 100 cases
.venv/bin/python -m student_agent.cli run

# 4. Kiểm tra hợp lệ dữ liệu đầu ra và Trace Logs
.venv/bin/python -m student_agent.cli validate

# 5. Đóng gói file nộp bài (Submission ZIP)
.venv/bin/python -m student_agent.cli package --output dist/submission.zip
```

