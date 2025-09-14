from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# =========================
# Payload 스키마: 문자열 3개
# =========================
class BusReport(BaseModel):
    vehicle_no: str = Field(alias="vehicleNo", description="차량번호")
    route: str = Field(description="운행중인 노선")
    stop_location: str = Field(alias="stopLocation", description="정류소 위치정보")

    class Config:
        populate_by_name = True     # vehicle_no 로도 주입 허용
        extra = "ignore"            # 여분 필드는 무시

# 수신 레코드(메모리 저장)
class StoredData(BaseModel):
    received_at: str
    source_ip: str
    payload: BusReport

_latest: Optional[StoredData] = None
_lock = asyncio.Lock()

# =========================
# FastAPI App
# =========================
app = FastAPI(title="Minimal Live Page (5s refresh, fixed schema)")

# =========================
# HTML: 5초 주기 갱신 페이지
# =========================
@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>실시간 차량 운행 모니터</title>
</head>
<body>
  <h1>실시간 차량 운행 데이터</h1>
  <p><b>수신 시각:</b> <span id="recv">데이터 없음</span></p>
  <p><b>송신 IP:</b> <span id="ip">-</span></p>
  <p><b>차량번호:</b> <span id="vehicleNo">-</span></p>
  <p><b>운행 노선:</b> <span id="route">-</span></p>
  <p><b>정류소 위치정보:</b> <span id="stopLocation">-</span></p>

  <h3>원본 JSON</h3>
  <pre id="payload" style="white-space: pre-wrap; word-break: break-all; background:#f6f6f6; padding:8px;"></pre>

  <script>
    async function refresh() {
      try {
        const res = await fetch("/data");
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();

        if (data && data.payload) {
          document.getElementById("recv").innerText = data.received_at || "-";
          document.getElementById("ip").innerText = data.source_ip || "-";

          // 서버가 snake_case 또는 alias(camelCase)로 보낼 수 있으니 둘 다 대응
          const p = data.payload;
          const vehicle = p.vehicleNo ?? p.vehicle_no ?? "-";
          const route = p.route ?? "-";
          const stopLoc = p.stopLocation ?? p.stop_location ?? "-";

          document.getElementById("vehicleNo").innerText = vehicle;
          document.getElementById("route").innerText = route;
          document.getElementById("stopLocation").innerText = stopLoc;

          document.getElementById("payload").innerText = JSON.stringify(p, null, 2);
        } else {
          document.getElementById("recv").innerText = "데이터 없음";
          document.getElementById("ip").innerText = "-";
          document.getElementById("vehicleNo").innerText = "-";
          document.getElementById("route").innerText = "-";
          document.getElementById("stopLocation").innerText = "-";
          document.getElementById("payload").innerText = "";
        }
      } catch (e) {
        console.error("갱신 실패:", e);
      }
    }

    refresh();                    // 즉시 1회
    setInterval(refresh, 5000);   // 5초 주기
  </script>
</body>
</html>
    """

# =========================
# 외부 데이터 수신 (POST /ingest)
# JSON 예시:
# {
#   "vehicleNo": "12가3456",
#   "route": "R-101",
#   "stopLocation": "SCH정문 북측"
# }
# =========================
@app.post("/ingest", response_model=StoredData)
async def ingest(payload: BusReport, request: Request) -> StoredData:
    client_ip = request.client.host if request.client else "unknown"
    record = StoredData(
        received_at=datetime.now().isoformat(timespec="seconds"),
        source_ip=client_ip,
        payload=payload,
    )
    async with _lock:
        global _latest
        _latest = record
    return record

# =========================
# 현재 저장된 데이터 조회 (GET /data)
# =========================
@app.get("/data", response_model=Optional[StoredData])
async def get_data() -> Optional[StoredData]:
    async with _lock:
        return _latest

def _read_json(path: str):
    path = Path(path)
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/update")
def get_db_json(orgID: int = Query(..., description="기관ID")):
    print("return db - orgID:", orgID)
    db = _read_json("data.json")
    return db

# (선택) 직접 실행용 엔트리포인트
if __name__ == "__main__":
    import os, uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "9443")), reload=True)
