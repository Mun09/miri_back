from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio
import os
from miri import run_analysis, run_analysis_stream  # Import your core logic


app = FastAPI()

# CORS configuration
# TEMPORARY: Allow all origins for testing
# TODO: Restrict to specific domains in production
# origins = ["*"]

# PRODUCTION CONFIGURATION (uncomment when ready):
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://miri-front.vercel.app",
]

frontend_url = os.getenv("FRONTEND_URL", "")
if frontend_url:
    origins.append(frontend_url)

# Log configured origins for debugging
print(f"🔒 CORS Configured Origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # Set to False when using "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# A simple request model
class IdeaRequest(BaseModel):
    idea: str

@app.get("/")
async def root():
    """Root endpoint for testing"""
    return {
        "status": "ok",
        "message": "MIRI Backend API is running",
        "version": "1.0",
        "endpoints": {
            "POST /analyze": "Analyze business idea"
        }
    }

@app.get("/health")
async def health_check():
    """Health check for Railway"""
    return {"status": "healthy", "service": "miri-backend"}

@app.post("/analyze")
async def analyze_idea(request: IdeaRequest):
    """
    Analyzes the business idea using the miri pipeline.
    Returns a stream of logs and the final result.
    """
    return StreamingResponse(run_analysis_stream(request.idea), media_type="application/x-ndjson")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
