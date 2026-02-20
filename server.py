from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio
import os
import json
from datetime import datetime
from miri import run_analysis, run_analysis_stream  # Import your core logic


from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
# TEMPORARY: Allow all origins for testing connection issues
# origins = ["*"]

# PRODUCTION CONFIGURATION (uncomment when ready):
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://miri-front.vercel.app",
]

# frontend_url = os.getenv("FRONTEND_URL", "")
# if frontend_url:
#     origins.append(frontend_url)

# Log configured origins for debugging
print(f"🔒 CORS Configured Origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A simple request model
class IdeaRequest(BaseModel):
    idea: str
    what_ifs: list[str] = []
    thread_id: str = "default_thread" # Default for backward compatibility

# [NEW] Simple Stats Manager
STATS_FILE = "usage_stats.json"

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"total_requests": 0, "history": []}
    return {"total_requests": 0, "history": []}

def save_stats(stats):
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Stats save error: {e}")

def increment_stats():
    stats = load_stats()
    stats["total_requests"] = stats.get("total_requests", 0) + 1
    # Optional: Log timestamp (keep last 100 for simplicity)
    stats.setdefault("history", []).append(datetime.now().isoformat())
    if len(stats["history"]) > 100:
        stats["history"] = stats["history"][-100:]
    save_stats(stats)
    return stats["total_requests"]

@app.get("/")
async def root():
    """Root endpoint for testing"""
    stats = load_stats()
    return {
        "status": "ok",
        "message": "MIRI Backend API is running",
        "version": "1.0",
        "stats": {
            "total_analyses": stats.get("total_requests", 0)
        },
        "endpoints": {
            "POST /analyze": "Analyze business idea",
            "GET /stats": "View usage statistics"
        }
    }

@app.get("/health")
async def health_check():
    """Health check for Railway"""
    return {"status": "healthy", "service": "miri-backend"}

@app.get("/stats")
async def get_stats():
    """Returns usage statistics"""
    return load_stats()

@app.post("/analyze")
@limiter.limit("5/minute")
async def analyze_idea(request: Request, idea_req: IdeaRequest):
    """
    Analyzes the business idea using the miri pipeline.
    Returns a stream of logs and the final result.
    """
    # Count the request
    increment_stats()
    
    return StreamingResponse(run_analysis_stream(idea_req.idea, idea_req.what_ifs, idea_req.thread_id), media_type="application/x-ndjson")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
