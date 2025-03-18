import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
import logging
from typing import List
from datetime import datetime
from narrative import (
    generate_underwriter_narrative,
    generate_and_verify_narrative,
    check_underwriter_narrative,
    get_underwriter_schema
)
from logic import (
    evaluate_borrower_type,
    evaluate_application
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
IS_STAGING = os.getenv("STAGING", "False").lower() == "true"

app = FastAPI(
    title="Loan Evaluation API",
    description="API for evaluating loan eligibility based on risk profiles, borrower checks, and SME risk rules.",
    version="1.0"
)

# -------------------------------
# Pydantic Models
# -------------------------------
class EvaluationDecision(BaseModel):
    decision: str
    confidence: float
    explanation: str

class NarrativeCheckRequest(BaseModel):
    evaluation: EvaluationDecision
    narrative: str

class BorrowerTypeRequest(BaseModel):
    borrower_type: str

class BorrowerIDVerificationRequest(BaseModel):
    is_verified: bool

class OpenBankingRequest(BaseModel):
    is_connected: bool

# SMERiskRequest includes fields required by evaluate_application from logic.py.
class SMERiskRequest(BaseModel):
    sme_profile: str = Field(alias="smeProfile")
    risk_profile: str = Field(alias="riskProfile")
    dscr: float = Field(alias="stressedDSCR")
    loan_amount: float = Field(alias="loanAmount")
    loan_type: str = Field(alias="loanType")
    industry_sector: str = Field(default="Wholesale and Retail Trade", alias="industrySector")
    provided_docs: List[str] = Field(default_factory=list, alias="providedDocs")
    # Additional fields (if needed by downstream logic) are kept for reference:
    provided_pg: float = Field(default=1.0, description="Fraction of required Personal Guarantee provided")
    min_pg_required: float = Field(default=0.20, description="Minimum required Personal Guarantee fraction")
    requires_debenture: bool = Field(default=False, description="Indicates if a Debenture is required")
    has_debenture: bool = Field(default=False, description="Indicates if a Debenture is provided")
    has_legal_charge: bool = Field(default=True, description="True if a Legal Charge is in place for secured loans")
    is_due_diligence_complete: bool = Field(default=True, description="True if AML/KYC and due diligence are complete")
    is_business_registered: bool = Field(default=True, description="True if business registration is verified")

# -------------------------------
# API Endpoints
# -------------------------------
@app.post("/evaluate/borrower-type")
async def evaluate_borrower_type_endpoint(request: BorrowerTypeRequest):
    return evaluate_borrower_type(request.borrower_type)

@app.post("/evaluate/sme-risk")
async def evaluate_sme_risk_endpoint(request: SMERiskRequest):
    try:
        result = evaluate_application(
            sme_profile=request.sme_profile,
            risk_profile=request.risk_profile,
            dscr=request.dscr,
            loan_amount=request.loan_amount,
            loan_type=request.loan_type,
            industry_sector=request.industry_sector,
            provided_docs=request.provided_docs
        )
        return result
    except Exception as e:
        logger.exception("Unexpected error during SME risk evaluation")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/underwriter-schema")
async def underwriter_schema_endpoint():
    if IS_STAGING:
        return get_underwriter_schema()
    else:
        return {
            "function_name": "getUnderwriterSchema",
            "domain": "loan-decision-api.onrender.com",
            "message": "The requested action requires approval",
            "action_id": "g-bebaea08fb7964507a70a86a705414e10fbe0f9b"
        }

@app.post("/generate-narrative")
async def generate_narrative_endpoint(evaluation: EvaluationDecision):
    try:
        narrative = generate_underwriter_narrative(evaluation.dict())
        return {"narrative": narrative}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-and-verify-narrative")
async def generate_and_verify_narrative_endpoint(evaluation: EvaluationDecision):
    try:
        narrative = generate_and_verify_narrative(evaluation.dict())
        return {"narrative": narrative}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/check-narrative")
async def check_narrative_endpoint(request: NarrativeCheckRequest):
    try:
        result = check_underwriter_narrative(request.narrative, request.evaluation.dict())
        return {"check_result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------
# Run the Application
# -------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
