import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from evaluation_module import (
    generate_underwriter_narrative,
    generate_and_verify_narrative,
    check_underwriter_narrative,
    evaluate_borrower_type,
    evaluate_borrower_id_verification,
    evaluate_open_banking,
    evaluate_sme_risk,
    get_underwriter_schema,
    UnderwriterSchemaModel,
    EvaluationError
)
from typing import Dict, List
from datetime import datetime
import uvicorn
import logging

# --------------------------------------------------
# Environment Detection
# --------------------------------------------------
# Check if running in a staging environment. In staging, auto-approval will bypass manual approval.
IS_STAGING = os.getenv("STAGING", "False").lower() == "true"

# --------------------------------------------------
# FastAPI App & Endpoints Setup
# --------------------------------------------------
app = FastAPI(
    title="Loan Evaluation API",
    description="API for evaluating loan eligibility based on risk profiles, borrower checks, and SME risk rules (Rules 1-70).",
    version="1.0"
)

# Define a Pydantic model for the evaluation decision
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

class SMERiskRequest(BaseModel):
    sme_profile: str = Field(alias="smeProfile")
    risk_profile: str = Field(alias="riskProfile")
    dscr: float = Field(alias="stressedDSCR")
    loan_amount: float = Field(alias="loanAmount")
    loan_type: str = Field(alias="loanType")
    provided_pg: float = Field(default=1.0, description="Fraction of required Personal Guarantee provided")
    min_pg_required: float = Field(default=0.20, description="Minimum required Personal Guarantee fraction")
    requires_debenture: bool = Field(default=False, description="Indicates if a Debenture is required")
    has_debenture: bool = Field(default=False, description="Indicates if a Debenture is provided")
    has_legal_charge: bool = Field(default=True, description="True if a Legal Charge is in place for secured loans")
    is_due_diligence_complete: bool = Field(default=True, description="True if AML/KYC and due diligence are complete")
    is_business_registered: bool = Field(default=True, description="True if business registration is verified")

@app.post("/evaluate/borrower-type")
async def evaluate_borrower_type_endpoint(request: BorrowerTypeRequest):
    return evaluate_borrower_type(request.borrower_type)

@app.post("/evaluate/borrower-id")
async def evaluate_borrower_id_endpoint(request: BorrowerIDVerificationRequest):
    try:
        result = evaluate_borrower_id_verification(request.is_verified)
        logger.info(f"Borrower ID Evaluation result: {result}")
        return result
    except EvaluationError as e:
        logger.error(f"Evaluation error in borrower ID verification: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error during borrower ID evaluation")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/evaluate/open-banking")
async def evaluate_open_banking_endpoint(request: OpenBankingRequest):
    return evaluate_open_banking(request.is_connected)

@app.post("/evaluate/sme-risk")
async def evaluate_sme_risk_endpoint(request: SMERiskRequest):
    return evaluate_sme_risk(
        sme_profile=request.sme_profile,
        risk_profile=request.risk_profile,
        dscr=request.dscr,
        loan_amount=request.loan_amount,
        loan_type=request.loan_type,
        provided_pg=request.provided_pg,
        min_pg_required=request.min_pg_required,
        requires_debenture=request.requires_debenture,
        has_debenture=request.has_debenture,
        has_legal_charge=request.has_legal_charge,
        is_due_diligence_complete=request.is_due_diligence_complete,
        is_business_registered=request.is_business_registered
    )

@app.get("/underwriter-schema", response_model=UnderwriterSchemaModel)
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

# --------------------------------------------------
# Run the Application
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
