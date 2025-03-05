from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal

app = FastAPI()

# Define request model
class LoanApplication(BaseModel):
    smeProfile: Literal["EB", "ESB", "NTB", "SU"]
    riskProfile: Literal["T1", "T2", "T3"]
    stressedDSCR: float
    loanAmount: float
    loanType: Literal["secured", "unsecured"]

# Decision rules logic
def evaluate_loan(application: LoanApplication):
    sme_profile = application.smeProfile
    risk_profile = application.riskProfile
    dscr = application.stressedDSCR
    loan_amount = application.loanAmount
    loan_type = application.loanType

    # Basic validation
    if loan_amount < 25001:
        return {"decision": "FAIL", "explanation": "Loan amount must be greater than £25,000."}

    # Decision rules
    if sme_profile == "EB" and risk_profile == "T1" and dscr > 150:
        return {"decision": "PASS", "explanation": "Strong financials and low risk profile."}
    elif sme_profile == "EB" and risk_profile == "T3" and dscr < 135:
        return {"decision": "FLAG/UW", "explanation": "Higher risk profile. Needs underwriter review."}
    elif sme_profile == "SU" and risk_profile == "T3" and dscr < 135:
        return {"decision": "FAIL", "explanation": "Startup with high risk profile does not qualify."}
    
    return {"decision": "FLAG/AI", "explanation": "Requires additional AI analysis for borderline cases."}

# API endpoint
@app.post("/evaluate")
async def evaluate(application: LoanApplication):
    result = evaluate_loan(application)
    return result
