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
origins = [
    "http://localhost:3000",  # Next.js frontend (local)
    "http://localhost:8000",
    "https://miri-front.vercel.app",  # Production frontend (update with your actual domain)
    os.getenv("FRONTEND_URL", ""),  # Allow custom frontend URL from env
]

# Filter out empty strings
origins = [origin for origin in origins if origin]

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

@app.get("/")
async def read_root():
    return {"message": "MIRI Backend API is running."}

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
