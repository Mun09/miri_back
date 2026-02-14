"""
MIRI - 법률 자문 AI 시스템 (모듈화된 버전)
Main entry point for the modularized MIRI Legal Advisory System

사용 예시:
    from pipeline import run_analysis_stream
    
    async for chunk in run_analysis_stream("법률 상담 내용"):
        print(chunk)
"""

# Import all modules
from config import IS_TEST, MOCK_RESULT
from models import *
from llm_client import llm_client
from law_api import law_api
from modules import Structurer, Simulator, Investigator, AdversarialDebate
from pipeline import run_analysis_stream, run_analysis

# Create global instances if needed
structurer = Structurer()
simulator = Simulator()
investigator = Investigator()
auditor = AdversarialDebate()

print("✅ MIRI Legal Advisory System Initialized (Modularized Version)")
print("✅ 법률 자문 AI 시스템 '미리(MIRI)' - 모든 법률 상담에 대응 가능")
print(f"✅ Test Mode: {IS_TEST}")

# Export main functions
__all__ = [
    'run_analysis_stream',
    'run_analysis',
    'structurer',
    'simulator',
    'investigator',
    'auditor'
]
