from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import json
from pathlib import Path
from datetime import date

# === 설정 ===
DATA_DIR = Path(__file__).parent / "data"
DB_FILE = DATA_DIR / "db.json"
DB_DATA = DATA_DIR / "data.json"
SCHEDULES_FILE = DATA_DIR / "schedules.json"

app = FastAPI(title="Shuttle-roid Test Server", version="1.0.0")

# (선택) CORS: 필요 없으면 주석 처리하셔도 됩니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발/테스트 용도
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 모델 ===
class UpdateCheckResponse(BaseModel):
    update: bool           # 서버 플래그가 클 경우 True
    clientFlag: int        # 클라이언트가 보낸 값
    serverFlag: int        # 서버 보유 최신 값

class DBResponse(BaseModel):
    updateFlag: int
    payload: Dict[str, Any]

class Trip(BaseModel):
    depTime: str
    routeId: int

class CarSchedule(BaseModel):
    carNo: str
    date: Optional[str] = None
    trips: List[Trip]

class ScheduleResponse(BaseModel):
    carNo: str
    date: Optional[str] = None
    trips: List[Trip]

# === 유틸 ===
def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"Server data file not found: {path.name}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in {path.name}: {e}")

# === 1) 업데이트 체크 ===
@app.get("/update/check", response_model=bool)
def check_update(flag: int = Query(..., description="단말 DB버전"), orgID: int = Query(...,description="기관ID")):
    db = _read_json(DB_FILE)
    server_flag = int(db.get("updateFlag", 0))
    return server_flag > flag

# === 2) 업데이트 요청(DB JSON 통째 반환) ===
@app.get("/update")
def get_db_json(orgID: int = Query(...,description="기관ID")):
    print("return db - orgID:", orgID)
    db = _read_json("data.json")
    return db

# === 3) 당일 운행 정보 요청 (차량번호 기준) ===
@app.get("/api/schedule/{car_no}", response_model=ScheduleResponse)
def get_schedule(car_no: str):
    schedules = _read_json(SCHEDULES_FILE).get("schedules", [])
    if not isinstance(schedules, list):
        raise HTTPException(status_code=500, detail="schedules.json must contain 'schedules' array")

    # 우선 날짜가 있으면 오늘 날짜 우선, 없으면 차량번호만 필터
    today_str = date.today().isoformat()
    candidates = [s for s in schedules if s.get("carNo") == car_no and s.get("date", today_str) == today_str]
    if not candidates:
        # 날짜 무시하고 차량번호만 보는 fallback
        candidates = [s for s in schedules if s.get("carNo") == car_no]

    if not candidates:
        raise HTTPException(status_code=404, detail=f"No schedule for carNo={car_no}")

    s = candidates[0]
    # 검증 및 모델 변환
    if "trips" not in s or not isinstance(s["trips"], list):
        raise HTTPException(status_code=500, detail="schedule item must contain 'trips' array")

    trips = [Trip(**t) for t in s["trips"]]
    return ScheduleResponse(carNo=s["carNo"], date=s.get("date"), trips=trips)
