import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List
from datetime import datetime
import uvicorn

# --------------------------------------------------
# Environment Detection
# --------------------------------------------------
# Check if running in a staging environment. In staging, auto-approval will bypass manual approval.
IS_STAGING = os.getenv("STAGING", "False").lower() == "true"

# --------------------------------------------------
# Underwriter Schema Models
# --------------------------------------------------
class UnderwriterInstructions(BaseModel):
    role: str
    objective: str
    prompt_guidelines: List[str]
    output_structure: Dict[str, str]

class UnderwriterSchemaModel(BaseModel):
    version: str
    instructions: UnderwriterInstructions
    data_sources: Dict[str, str]
    fallback: str

# --------------------------------------------------
# Underwriter Schema Definition
# --------------------------------------------------
UNDERWRITER_SCHEMA = {
    "version": "3.0",
    "instructions": {
        "role": "Underwriter GPT",
        "objective": (
            "Generate a comprehensive explanation for an auto-approved loan application by analyzing the complete input scenario data "
            "against a set of business rules, risk metrics, and regulatory requirements. Your explanation must detail the decision-making process, "
            "include an audit trail with rule versioning and timestamps, and reference specific rule IDs, thresholds, and risk adjustments for full transparency and compliance."
        ),
        "prompt_guidelines": [
            "Begin with a 'Decisioning Summary' that states the final decision (PASS, FLAG/AI, FLAG/UW, FAIL, or REQUIREMENT) and the overall confidence rating.",
            "Include a 'Business Logic Explanation' section detailing all key rules, risk adjustments, and calculations applied. Reference specific rule IDs and thresholds where applicable.",
            "Provide an 'Input Scenario Analysis' section summarizing the complete input data, including SME profile, risk profile, DSCR, loan amount, loan type, borrower type, credit checks, and verification statuses.",
            "Enumerate any triggered deterministic rules along with detailed explanations of their impact on the decision.",
            "Include 'Risk Mitigation Recommendations' outlining any additional security measures or manual review requirements for borderline cases.",
            "Add an 'Audit Information' section that records the rule version, evaluation timestamp, and a log of the decision-making process.",
            "Include 'Compliance Notes' that describe adherence to regulatory guidelines and internal lending policies, noting any deviations.",
            "If any required data is missing or ambiguous, clearly indicate which data points are incomplete and default to flagging the application for manual review.",
            "Format your output using clearly defined headings and structure in JSON or YAML."
        ],
        "output_structure": {
            "decisioning_summary": "A concise overview of the final decision and the associated confidence rating.",
            "business_logic_explanation": "A detailed breakdown of the applied business rules, risk adjustments, and calculations, including references to specific rule IDs.",
            "input_scenario_analysis": "A summary of all provided input data used in the evaluation.",
            "applied_rules": "A list of triggered deterministic rules with their IDs and detailed explanations of how they impacted the decision.",
            "risk_recommendations": "Recommendations for mitigating risks, including additional security requirements or notes for manual review if the case is borderline.",
            "audit_information": "Metadata including the rule version, evaluation timestamp, and an audit trail of all decisions made.",
            "compliance_notes": "Notes confirming adherence to regulatory requirements and internal lending policies, along with any documented exceptions."
        }
    },
   "data_sources": {
    "decisioning_gpt": "This process is self-referential; the same GPT that generates the decision is used to provide a detailed explanation of the applied business logic using the input scenario data.",
    "external_data": "Includes verifications from external sources such as credit bureaus, open banking data, financial statements, and borrower identity checks."
},
    "fallback": (
        "If any required data from the input scenario is missing, ambiguous, or fails verification, default to flagging the application for manual review. "
        "Clearly note which data points were insufficient and recommend obtaining additional information."
    ),
    "audit_and_versioning": {
        "rule_version": "3.0",
        "timestamp": "To be recorded at evaluation time",
        "audit_trail": "A detailed log of all input data, applied rules, risk adjustments, and the final decision for compliance and regulatory review."
    },
    "compliance_notes": (
        "Ensure that the decision explanation adheres to internal lending policies and external regulatory guidelines. "
        "Any deviations must be clearly documented with appropriate justifications."
    )
}

def get_underwriter_schema():
    """
    Return the comprehensive underwriter schema containing instructions,
    output structure, data source references, fallback guidelines, and dynamic audit metadata.
    Updates the audit timestamp at runtime.
    """
    schema = UNDERWRITER_SCHEMA.copy()
    if "audit_and_versioning" in schema:
        schema["audit_and_versioning"]["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return schema

# --------------------------------------------------
# Configuration & Business Logic
# --------------------------------------------------
CONFIG = {"loan_adjustment_factor": 0.10}

RISK_PROFILES = {
    "T1": {"label": "Low Risk", "missed_payments": (0, 1), "ccjs_defaults": (0, 2500), "iva_liquidation_years": 5, "confidence": 0.95},
    "T2": {"label": "Medium Risk", "missed_payments": (0, 2), "ccjs_defaults": (2500, 3000), "iva_liquidation_years": 5, "confidence": 0.85},
    "T3": {"label": "High Risk", "missed_payments": (3, float('inf')), "ccjs_defaults": (3000, 5000), "iva_liquidation_years": 5, "confidence": 0.70}
}

SME_PROFILES = {
    "EB": {"label": "Established Business", "financials_required": ["3 years certified accounts", "2 years accounts + 12-month forecast"], "loan_unsecured_min": 25000, "loan_unsecured_max": 200000, "loan_secured_max": 250000, "confidence": 0.95},
    "ESB": {"label": "Early-Stage Business", "financials_required": ["1 year certified accounts", "12+ months management accounts"], "loan_unsecured_min": 25000, "loan_unsecured_max": 80000, "loan_secured_max": 150000, "confidence": 0.85},
    "NTB": {"label": "Newly Trading Business", "financials_required": ["3-11 months management accounts"], "loan_unsecured_min": 25000, "loan_unsecured_max": 60000, "loan_secured_max": 100000, "confidence": 0.75},
    "SU": {"label": "Startup", "financials_required": ["No management accounts, pre-revenue"], "loan_unsecured_min": 26000, "loan_unsecured_max": 40000, "loan_secured_max": 80000, "confidence": 0.60}
}

RISK_CONFIDENCE_ADJUSTMENTS = {"T1": 0.10, "T2": 0.00, "T3": -0.15}
DSCR_CONFIDENCE_ADJUSTMENTS = {"low": -0.15, "medium": 0.00, "high": 0.10}

def adjust_confidence(base_confidence: float, requested_loan: float, min_loan: float, max_loan: float,
                      risk_profile: str, dscr_level: str) -> float:
    factor = CONFIG["loan_adjustment_factor"]
    denominator = max_loan - min_loan if max_loan != min_loan else 1
    reduction = ((requested_loan - min_loan) / denominator) * factor
    loan_conf = max(base_confidence - reduction, 0.50)
    risk_conf = loan_conf + RISK_CONFIDENCE_ADJUSTMENTS.get(risk_profile, 0)
    final_conf = risk_conf + DSCR_CONFIDENCE_ADJUSTMENTS.get(dscr_level, 0)
    return max(min(final_conf, 1.00), 0.50)

def evaluate_borrower_type(borrower_type: str) -> dict:
    allowed = {"LTD", "Sole Trader", "LLP"}
    if borrower_type in allowed:
        return {"decision": "PASS", "confidence": 0.95,
                "explanation": f"Borrower type {borrower_type} is accepted."}
    return {"decision": "FAIL", "confidence": 0.99,
            "explanation": f"Borrower type {borrower_type} is not allowed."}

def evaluate_borrower_id_verification(is_verified: bool) -> dict:
    if is_verified:
        return {"decision": "PASS", "confidence": 0.98,
                "explanation": "Borrower ID has been verified."}
    return {"decision": "CONDITIONAL APPROVAL", "confidence": 0.99,
            "explanation": "Loan approved on condition that borrower provides valid ID verification before funding."}

def evaluate_open_banking(is_connected: bool) -> dict:
    if is_connected:
        return {"decision": "PASS", "confidence": 0.95,
                "explanation": "Open banking is connected."}
    return {"decision": "CONDITIONAL APPROVAL", "confidence": 0.99,
            "explanation": "Loan approved on condition that the borrower successfully connects Open Banking before funding."}

def global_sme_checks(dscr: float, loan_amount: float) -> dict:
    if dscr < 125:
        return {"decision": "FAIL", "confidence": 0.99, "explanation": "DSCR <125%. Loan declined."}
    if loan_amount < 25001:
        return {"decision": "FAIL", "confidence": 0.99, "explanation": "Loan amount below £25,001. Does not meet minimum threshold."}
    return {}

def evaluate_eb_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    base_conf = SME_PROFILES["EB"]["confidence"]
    min_loan = SME_PROFILES["EB"]["loan_unsecured_min"]
    max_loan = SME_PROFILES["EB"]["loan_secured_max"]
    if risk_profile == "T1" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.90, "explanation": "EB/T1 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "PASS", "confidence": 0.92, "explanation": "EB/T1 with DSCR >150% qualifies for a secured loan."}
    if risk_profile == "T2" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.87, "explanation": "EB/T2 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "PASS", "confidence": 0.89, "explanation": "EB/T2 with DSCR >150% qualifies for a secured loan."}
    if risk_profile == "T3" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 100000:
            return {"decision": "FLAG/AI", "confidence": 0.75, "explanation": "EB/T3 with DSCR >150% (unsecured): AI review required."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "FLAG/AI", "confidence": 0.78, "explanation": "EB/T3 with DSCR >150% (secured): AI review required."}
    if risk_profile == "T1" and 1.349 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.85, "explanation": "EB/T1 with DSCR just below 150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "PASS", "confidence": 0.88, "explanation": "EB/T1 with DSCR just below 150% qualifies for a secured loan."}
    if 1.349 < dscr <= 1.50:
        if risk_profile == "T2":
            if loan_type == "unsecured" and loan_amount <= 100000:
                return {"decision": "PASS", "confidence": 0.80, "explanation": "EB/T2 with DSCR just below 150% qualifies for an unsecured loan."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "PASS", "confidence": 0.83, "explanation": "EB/T2 with DSCR just below 150% qualifies for a secured loan."}
        if risk_profile == "T3":
            if loan_type == "unsecured" and loan_amount <= 75000:
                return {"decision": "FLAG/UW", "confidence": 0.70, "explanation": "EB/T3 with DSCR just below 150%: underwriter review required (unsecured)."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "FLAG/UW", "confidence": 0.72, "explanation": "EB/T3 with DSCR just below 150%: underwriter review required (secured)."}
    if 1.25 < dscr <= 1.35:
        if risk_profile == "T1":
            if loan_type == "unsecured" and loan_amount <= 100000:
                return {"decision": "PASS", "confidence": 0.78, "explanation": "EB/T1 with DSCR between 125%-135% qualifies for an unsecured loan."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "PASS", "confidence": 0.82, "explanation": "EB/T1 with DSCR between 125%-135% qualifies for a secured loan."}
        if risk_profile == "T2":
            if loan_type == "unsecured" and loan_amount <= 75000:
                return {"decision": "PASS", "confidence": 0.75, "explanation": "EB/T2 with DSCR between 125%-135% qualifies for an unsecured loan."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "PASS", "confidence": 0.79, "explanation": "EB/T2 with DSCR between 125%-135% qualifies for a secured loan."}
        if risk_profile == "T3":
            if loan_type == "unsecured" and loan_amount <= 50000:
                return {"decision": "FLAG/AI", "confidence": 0.65, "explanation": "EB/T3 with DSCR between 125%-135%: AI review required (unsecured)."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "FLAG/UW", "confidence": 0.70, "explanation": "EB/T3 with DSCR between 125%-135%: underwriter review required (secured)."}
    return {"decision": "REQUIREMENT", "confidence": 0.99, "explanation": "Debenture and a minimum of 20% personal guarantee (PG) required."}

def evaluate_esb_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    if risk_profile == "T1" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 80000:
            return {"decision": "PASS", "confidence": 0.88, "explanation": "ESB/T1 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.90, "explanation": "ESB/T1 with DSCR >150% qualifies for a secured loan."}
    if risk_profile == "T2" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 75000:
            return {"decision": "PASS", "confidence": 0.85, "explanation": "ESB/T2 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.87, "explanation": "ESB/T2 with DSCR >150% qualifies for a secured loan."}
    if risk_profile == "T3" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "FLAG/AI", "confidence": 0.70, "explanation": "ESB/T3 with DSCR >150% (unsecured): AI review required."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72, "explanation": "ESB/T3 with DSCR >150% (secured): underwriter review required."}
    if risk_profile == "T1" and 1.35 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 80000:
            return {"decision": "PASS", "confidence": 0.85, "explanation": "ESB/T1 with DSCR between 135%-150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.87, "explanation": "ESB/T1 with DSCR between 135%-150% qualifies for a secured loan."}
    if risk_profile == "T2" and 1.35 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 75000:
            return {"decision": "PASS", "confidence": 0.82, "explanation": "ESB/T2 with DSCR between 135%-150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.85, "explanation": "ESB/T2 with DSCR between 135%-150% qualifies for a secured loan."}
    if risk_profile == "T3" and 1.349 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 50000:
            return {"decision": "FLAG/AI", "confidence": 0.70, "explanation": "ESB/T3 with DSCR between 135%-150%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72, "explanation": "ESB/T3 with DSCR between 135%-150%: underwriter review required (secured)."}
    if risk_profile == "T1" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "PASS", "confidence": 0.80, "explanation": "ESB/T1 with DSCR between 125%-135% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.83, "explanation": "ESB/T1 with DSCR between 125%-135% qualifies for a secured loan."}
    if risk_profile == "T2" and 1.25 < dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 50000:
            return {"decision": "PASS", "confidence": 0.75, "explanation": "ESB/T2 with DSCR >125% and <135% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.78, "explanation": "ESB/T2 with DSCR >125% and <135% qualifies for a secured loan."}
    if risk_profile == "T3" and 1.25 < dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.70, "explanation": "ESB/T3 with DSCR >125% and <135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72, "explanation": "ESB/T3 with DSCR >125% and <135%: underwriter review required (secured)."}
    return {"decision": "REQUIREMENT", "confidence": 0.99, "explanation": "Debenture and a minimum of 25% personal guarantee (PG) required."}

def evaluate_ntb_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    if risk_profile == "T1" and dscr > 1.25:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "PASS", "confidence": 0.80, "explanation": "NTB/T1 with DSCR >125% qualifies for an unsecured loan."}
        if loan_type == "secured" and dscr > 1.50 and loan_amount <= 100000:
            return {"decision": "PASS", "confidence": 0.85, "explanation": "NTB/T1 with DSCR >150% qualifies for a secured loan."}
    if risk_profile == "T2" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "PASS", "confidence": 0.78, "explanation": "NTB/T2 with DSCR >135% qualifies for an unsecured loan."}
        if loan_type == "secured" and dscr > 1.50 and loan_amount <= 100000:
            return {"decision": "PASS", "confidence": 0.80, "explanation": "NTB/T2 with DSCR >150% qualifies for a secured loan."}
    if risk_profile == "T3" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "FLAG/AI", "confidence": 0.70, "explanation": "NTB/T3 with DSCR >135%: AI review required (unsecured)."}
        if loan_type == "secured" and dscr > 1.25 and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72, "explanation": "NTB/T3 with DSCR >125%: underwriter review required (secured)."}
    if risk_profile == "T3" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.70, "explanation": "NTB/T3 with DSCR between 125%-135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72, "explanation": "NTB/T3 with DSCR between 125%-135%: underwriter review required (secured)."}
    return {"decision": "REQUIREMENT", "confidence": 0.99, "explanation": "Debenture and a minimum of 50% personal guarantee (PG) required."}

def evaluate_su_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    if risk_profile == "T1" and dscr > 1.349:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "PASS", "confidence": 0.78, "explanation": "SU/T1 with DSCR >135% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "PASS", "confidence": 0.82, "explanation": "SU/T1 with DSCR >135% qualifies for a secured loan."}
    if risk_profile == "T2" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.72, "explanation": "SU/T2 with DSCR >135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FLAG/AI", "confidence": 0.75, "explanation": "SU/T2 with DSCR >135%: AI review required (secured)."}
    if risk_profile == "T3" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/UW", "confidence": 0.70, "explanation": "SU/T3 with DSCR >135%: underwriter review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FLAG/UW", "confidence": 0.73, "explanation": "SU/T3 with DSCR >135%: underwriter review required (secured)."}
    if risk_profile == "T1" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.70, "explanation": "SU/T1 with DSCR between 125%-135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FLAG/AI", "confidence": 0.73, "explanation": "SU/T1 with DSCR between 125%-135%: AI review required (secured)."}
    if risk_profile == "T2" and dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FAIL", "confidence": 0.99, "explanation": "SU/T2 with DSCR <135% (unsecured): Loan declined."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FAIL", "confidence": 0.99, "explanation": "SU/T2 with DSCR <135% (secured): Loan declined."}
    if risk_profile == "T3" and dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 26000:
            return {"decision": "FAIL", "confidence": 0.99, "explanation": "SU/T3 with DSCR <135% (unsecured): Loan declined."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FAIL", "confidence": 0.99, "explanation": "SU/T3 with DSCR <135% (secured): Loan declined."}
    return {"decision": "REQUIREMENT", "confidence": 0.99, "explanation": "Debenture and a minimum of 50% personal guarantee (PG) required."}

def evaluate_sme_risk(sme_profile: str, risk_profile: str, dscr: float, loan_amount: float, loan_type: str,
                      provided_pg: float, min_pg_required: float, requires_debenture: bool, has_debenture: bool,
                      has_legal_charge: bool, is_due_diligence_complete: bool, is_business_registered: bool) -> dict:
    # Global Checks
    global_result = global_sme_checks(dscr, loan_amount)
    if global_result:
        return global_result

    # Conditional approvals for additional requirements:
    if sme_profile in ["SU", "NTB", "ESB"] and provided_pg < min_pg_required:
        return {"decision": "CONDITIONAL APPROVAL", "confidence": 0.99,
                "explanation": f"Loan approved on condition that a minimum {int(min_pg_required*100)}% Personal Guarantee (PG) is signed before funding."}
    if sme_profile in ["NTB", "ESB", "EB"] and requires_debenture and not has_debenture:
        return {"decision": "CONDITIONAL APPROVAL", "confidence": 0.99,
                "explanation": "Loan approved on condition that a Debenture is signed before funding."}
    if loan_type == "secured" and not has_legal_charge:
        return {"decision": "CONDITIONAL APPROVAL", "confidence": 0.99,
                "explanation": "Loan approved on condition that the lender obtains a Legal Charge (First or Second) over the security before funding."}
    if not is_due_diligence_complete:
        return {"decision": "CONDITIONAL APPROVAL", "confidence": 0.99,
                "explanation": "Loan approved on condition that all AML/KYC and Due Diligence checks are successfully completed before funding."}
    if not is_business_registered:
        return {"decision": "CONDITIONAL APPROVAL", "confidence": 0.99,
                "explanation": "Loan approved on condition that borrower provides proof of business registration before funding."}

    # Proceed to profile-specific evaluation:
    if sme_profile == "EB":
        return evaluate_eb_risk(risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "ESB":
        return evaluate_esb_risk(risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "NTB":
        return evaluate_ntb_risk(risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "SU":
        return evaluate_su_risk(risk_profile, dscr, loan_amount, loan_type)
    else:
        return {"decision": "FAIL", "confidence": 0.99, "explanation": "Invalid SME profile."}

# --------------------------------------------------
# FastAPI App & Endpoints Setup
# --------------------------------------------------
app = FastAPI(
    title="Loan Evaluation API",
    description="API for evaluating loan eligibility based on risk profiles, borrower checks, and SME risk rules (Rules 1-70).",
    version="1.0"
)

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
    return evaluate_borrower_id_verification(request.is_verified)

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

# --------------------------------------------------
# Run the Application
# --------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
