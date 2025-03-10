from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal
import uvicorn

# ---------------------- CONFIGURATION ----------------------
CONFIG = {"loan_adjustment_factor": 0.10}

RISK_PROFILES = {
    "T1": {
        "label": "Low Risk",
        "missed_payments": (0, 1),
        "ccjs_defaults": (0, 2500),  # Ensuring consistency
        "iva_liquidation_years": 5,
        "confidence": 0.95
    },
    "T2": {
        "label": "Medium Risk",
        "missed_payments": (0, 2),
        "ccjs_defaults": (2500, 3000),  # Ensuring consistency
        "iva_liquidation_years": 5,
        "confidence": 0.85
    },
    "T3": {
        "label": "High Risk",
        "missed_payments": (3, float('inf')),
        "ccjs_defaults": (3000, 5000),
        "iva_liquidation_years": 5,
        "confidence": 0.70
    }
}

SME_PROFILES = {
    "EB": {
        "label": "Established Business",
        "financials_required": ["3 years certified accounts", "2 years accounts + 12-month forecast"],
        "loan_unsecured_min": 25000,
        "loan_unsecured_max": 200000,
        "loan_secured_max": 250000,
        "confidence": 0.95
    },
    "ESB": {
        "label": "Early-Stage Business",
        "financials_required": ["1 year certified accounts", "12+ months management accounts"],
        "loan_unsecured_min": 25000,
        "loan_unsecured_max": 80000,
        "loan_secured_max": 150000,
        "confidence": 0.85
    },
    "NTB": {
        "label": "Newly Trading Business",
        "financials_required": ["3-11 months management accounts"],
        "loan_unsecured_min": 25000,
        "loan_unsecured_max": 60000,
        "loan_secured_max": 100000,
        "confidence": 0.75
    },
    "SU": {
        "label": "Startup",
        "financials_required": ["No management accounts, pre-revenue"],
        "loan_unsecured_min": 26000,
        "loan_unsecured_max": 40000,
        "loan_secured_max": 80000,
        "confidence": 0.60
    }
}

RISK_CONFIDENCE_ADJUSTMENTS = {
    "T1": 0.10,  # Low risk → Small confidence boost
    "T2": 0.00,  # Medium risk → No change
    "T3": -0.15  # High risk → Reduce confidence
}

DSCR_CONFIDENCE_ADJUSTMENTS = {
    "low": -0.15,   # Low DSCR → Reduce confidence
    "medium": 0.00, # Medium DSCR → No change
    "high": 0.10    # High DSCR → Increase confidence
}

# ---------------------- BUSINESS LOGIC ----------------------
def adjust_confidence(base_confidence: float, requested_loan: float, min_loan: float, max_loan: float,
                      risk_profile: str, dscr_level: str) -> float:
    """
    Adjust confidence based on:
      1. Loan amount requested (higher amount → lower confidence)
      2. Risk profile (higher risk → lower confidence)
      3. DSCR level (higher DSCR → higher confidence)
    """
    factor = CONFIG["loan_adjustment_factor"]
    denominator = max_loan - min_loan if max_loan != min_loan else 1  # Prevent division by zero
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
    return {"decision": "FAIL", "confidence": 0.99,
            "explanation": "Borrower ID has not been verified."}

def evaluate_open_banking(is_connected: bool) -> dict:
    if is_connected:
        return {"decision": "PASS", "confidence": 0.95,
                "explanation": "Open banking is connected."}
    return {"decision": "FAIL", "confidence": 0.99,
            "explanation": "Open banking is not connected."}

# --- Global checks common to all SME risk evaluations ---
def global_sme_checks(dscr: float, loan_amount: float) -> dict:
    if dscr < 1.25:
        return {"decision": "FAIL", "confidence": 0.99, "explanation": "DSCR <125%. Loan declined."}
    if loan_amount < 25001:
        return {"decision": "FAIL", "confidence": 0.99, "explanation": "Loan amount below £25,001. Does not meet minimum threshold."}
    return {}

# --- SME Profile Specific Functions ---
def evaluate_eb_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    base_conf = SME_PROFILES["EB"]["confidence"]
    min_loan = SME_PROFILES["EB"]["loan_unsecured_min"]
    max_loan = SME_PROFILES["EB"]["loan_secured_max"]

    # Rule 9-10: EB, T1, DSCR >150%
    if risk_profile == "T1" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.90,
                    "explanation": "EB/T1 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "PASS", "confidence": 0.92,
                    "explanation": "EB/T1 with DSCR >150% qualifies for a secured loan."}

    # Rule 11-12: EB, T2, DSCR >150%
    if risk_profile == "T2" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.87,
                    "explanation": "EB/T2 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "PASS", "confidence": 0.89,
                    "explanation": "EB/T2 with DSCR >150% qualifies for a secured loan."}

    # Rule 13-14: EB, T3, DSCR >150% → FLAG/AI
    if risk_profile == "T3" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 100000:
            return {"decision": "FLAG/AI", "confidence": 0.75,
                    "explanation": "EB/T3 with DSCR >150% (unsecured): AI review required."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "FLAG/AI", "confidence": 0.78,
                    "explanation": "EB/T3 with DSCR >150% (secured): AI review required."}

    # Rule 15-16: EB, T1, DSCR between 134.9% and 150%
    if risk_profile == "T1" and 1.349 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.85,
                    "explanation": "EB/T1 with DSCR just below 150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 250000:
            return {"decision": "PASS", "confidence": 0.88,
                    "explanation": "EB/T1 with DSCR just below 150% qualifies for a secured loan."}

    # Rule 17-20: EB, T2/T3, DSCR between 134.9 and 150
    if 1.349 < dscr <= 1.50:
        if risk_profile == "T2":
            if loan_type == "unsecured" and loan_amount <= 100000:
                return {"decision": "PASS", "confidence": 0.80,
                        "explanation": "EB/T2 with DSCR just below 150% qualifies for an unsecured loan."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "PASS", "confidence": 0.83,
                        "explanation": "EB/T2 with DSCR just below 150% qualifies for a secured loan."}
        if risk_profile == "T3":
            if loan_type == "unsecured" and loan_amount <= 75000:
                return {"decision": "FLAG/UW", "confidence": 0.70,
                        "explanation": "EB/T3 with DSCR just below 150%: underwriter review required (unsecured)."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "FLAG/UW", "confidence": 0.72,
                        "explanation": "EB/T3 with DSCR just below 150%: underwriter review required (secured)."}

    # Rule 21-26: EB, DSCR between 125 and 135%
    if 1.25 < dscr <= 1.35:
        if risk_profile == "T1":
            if loan_type == "unsecured" and loan_amount <= 100000:
                return {"decision": "PASS", "confidence": 0.78,
                        "explanation": "EB/T1 with DSCR between 125%-135% qualifies for an unsecured loan."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "PASS", "confidence": 0.82,
                        "explanation": "EB/T1 with DSCR between 125%-135% qualifies for a secured loan."}
        if risk_profile == "T2":
            if loan_type == "unsecured" and loan_amount <= 75000:
                return {"decision": "PASS", "confidence": 0.75,
                        "explanation": "EB/T2 with DSCR between 125%-135% qualifies for an unsecured loan."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "PASS", "confidence": 0.79,
                        "explanation": "EB/T2 with DSCR between 125%-135% qualifies for a secured loan."}
        if risk_profile == "T3":
            if loan_type == "unsecured" and loan_amount <= 50000:
                return {"decision": "FLAG/AI", "confidence": 0.65,
                        "explanation": "EB/T3 with DSCR between 125%-135%: AI review required (unsecured)."}
            if loan_type == "secured" and loan_amount <= 250000:
                return {"decision": "FLAG/UW", "confidence": 0.70,
                        "explanation": "EB/T3 with DSCR between 125%-135%: underwriter review required (secured)."}

    # Default for EB if no rule applies: Personal guarantee requirement.
    return {"decision": "REQUIREMENT", "confidence": 0.99,
            "explanation": "Debenture and a minimum of 20% personal guarantee (PG) required."}

def evaluate_esb_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    # Rule 27-28: ESB, T1, DSCR >150%
    if risk_profile == "T1" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 80000:
            return {"decision": "PASS", "confidence": 0.88,
                    "explanation": "ESB/T1 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.90,
                    "explanation": "ESB/T1 with DSCR >150% qualifies for a secured loan."}

    # Rule 29-30: ESB, T2, DSCR >150%
    if risk_profile == "T2" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 75000:
            return {"decision": "PASS", "confidence": 0.85,
                    "explanation": "ESB/T2 with DSCR >150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.87,
                    "explanation": "ESB/T2 with DSCR >150% qualifies for a secured loan."}

    # Rule 31-32: ESB, T3, DSCR >150%
    if risk_profile == "T3" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "FLAG/AI", "confidence": 0.70,
                    "explanation": "ESB/T3 with DSCR >150% (unsecured): AI review required."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72,
                    "explanation": "ESB/T3 with DSCR >150% (secured): underwriter review required."}

    # Rule 33-34: ESB, T1, DSCR between 135 and 150%
    if risk_profile == "T1" and 1.35 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 80000:
            return {"decision": "PASS", "confidence": 0.85,
                    "explanation": "ESB/T1 with DSCR between 135%-150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.87,
                    "explanation": "ESB/T1 with DSCR between 135%-150% qualifies for a secured loan."}

    # Rule 35-36: ESB, T2, DSCR between 135 and 150%
    if risk_profile == "T2" and 1.35 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 75000:
            return {"decision": "PASS", "confidence": 0.82,
                    "explanation": "ESB/T2 with DSCR between 135%-150% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.85,
                    "explanation": "ESB/T2 with DSCR between 135%-150% qualifies for a secured loan."}

    # Rule 37-38: ESB, T3, DSCR between 135 and 150%
    if risk_profile == "T3" and 1.349 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 50000:
            return {"decision": "FLAG/AI", "confidence": 0.70,
                    "explanation": "ESB/T3 with DSCR between 135%-150%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72,
                    "explanation": "ESB/T3 with DSCR between 135%-150%: underwriter review required (secured)."}

    # Rule 39-40: ESB, T1, DSCR between 125 and 135%
    if risk_profile == "T1" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "PASS", "confidence": 0.80,
                    "explanation": "ESB/T1 with DSCR between 125%-135% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.83,
                    "explanation": "ESB/T1 with DSCR between 125%-135% qualifies for a secured loan."}

    # Rule 41-42: ESB, T2, DSCR between 125 and less than 135%
    if risk_profile == "T2" and 1.25 < dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 50000:
            return {"decision": "PASS", "confidence": 0.75,
                    "explanation": "ESB/T2 with DSCR >125% and <135% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "PASS", "confidence": 0.78,
                    "explanation": "ESB/T2 with DSCR >125% and <135% qualifies for a secured loan."}

    # Rule 43-44: ESB, T3, DSCR between 125 and less than 135%
    if risk_profile == "T3" and 1.25 < dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.70,
                    "explanation": "ESB/T3 with DSCR >125% and <135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72,
                    "explanation": "ESB/T3 with DSCR >125% and <135%: underwriter review required (secured)."}

    # Default for ESB if no rule applies.
    return {"decision": "REQUIREMENT", "confidence": 0.99,
            "explanation": "Debenture and a minimum of 25% personal guarantee (PG) required."}

def evaluate_ntb_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    # Rule 45-46: NTB, T1, DSCR >125%
    if risk_profile == "T1" and dscr > 1.25:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "PASS", "confidence": 0.80,
                    "explanation": "NTB/T1 with DSCR >125% qualifies for an unsecured loan."}
        if loan_type == "secured" and dscr > 1.50 and loan_amount <= 100000:
            return {"decision": "PASS", "confidence": 0.85,
                    "explanation": "NTB/T1 with DSCR >150% qualifies for a secured loan."}

    # Rule 47-48: NTB, T2, DSCR >135%
    if risk_profile == "T2" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "PASS", "confidence": 0.78,
                    "explanation": "NTB/T2 with DSCR >135% qualifies for an unsecured loan."}
        if loan_type == "secured" and dscr > 1.50 and loan_amount <= 100000:
            return {"decision": "PASS", "confidence": 0.80,
                    "explanation": "NTB/T2 with DSCR >150% qualifies for a secured loan."}

    # Rule 49-50: NTB, T3, DSCR >135%
    if risk_profile == "T3" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            return {"decision": "FLAG/AI", "confidence": 0.70,
                    "explanation": "NTB/T3 with DSCR >135%: AI review required (unsecured)."}
        if loan_type == "secured" and dscr > 1.25 and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72,
                    "explanation": "NTB/T3 with DSCR >125%: underwriter review required (secured)."}

    # Rule 51-52: NTB, T3, DSCR between 125 and 135%
    if risk_profile == "T3" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.70,
                    "explanation": "NTB/T3 with DSCR between 125%-135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 150000:
            return {"decision": "FLAG/UW", "confidence": 0.72,
                    "explanation": "NTB/T3 with DSCR between 125%-135%: underwriter review required (secured)."}

    return {"decision": "REQUIREMENT", "confidence": 0.99,
            "explanation": "Debenture and a minimum of 50% personal guarantee (PG) required."}

def evaluate_su_risk(risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    # Rule 53-54: SU, T1, DSCR >135%
    if risk_profile == "T1" and dscr > 1.349:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "PASS", "confidence": 0.78,
                    "explanation": "SU/T1 with DSCR >135% qualifies for an unsecured loan."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "PASS", "confidence": 0.82,
                    "explanation": "SU/T1 with DSCR >135% qualifies for a secured loan."}

    # Rule 55-56: SU, T2, DSCR >135%
    if risk_profile == "T2" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.72,
                    "explanation": "SU/T2 with DSCR >135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FLAG/AI", "confidence": 0.75,
                    "explanation": "SU/T2 with DSCR >135%: AI review required (secured)."}

    # Rule 57-58: SU, T3, DSCR >135%
    if risk_profile == "T3" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/UW", "confidence": 0.70,
                    "explanation": "SU/T3 with DSCR >135%: underwriter review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FLAG/UW", "confidence": 0.73,
                    "explanation": "SU/T3 with DSCR >135%: underwriter review required (secured)."}

    # Rule 59-60: SU, T1, DSCR between 125 and 135%
    if risk_profile == "T1" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FLAG/AI", "confidence": 0.70,
                    "explanation": "SU/T1 with DSCR between 125%-135%: AI review required (unsecured)."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FLAG/AI", "confidence": 0.73,
                    "explanation": "SU/T1 with DSCR between 125%-135%: AI review required (secured)."}

    # Rule 61-62: SU, T2, DSCR <135% → FAIL
    if risk_profile == "T2" and dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            return {"decision": "FAIL", "confidence": 0.99,
                    "explanation": "SU/T2 with DSCR <135% (unsecured): Loan declined."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FAIL", "confidence": 0.99,
                    "explanation": "SU/T2 with DSCR <135% (secured): Loan declined."}

    # Rule 63-64: SU, T3, DSCR <135% → FAIL
    if risk_profile == "T3" and dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 26000:
            return {"decision": "FAIL", "confidence": 0.99,
                    "explanation": "SU/T3 with DSCR <135% (unsecured): Loan declined."}
        if loan_type == "secured" and loan_amount <= 80000:
            return {"decision": "FAIL", "confidence": 0.99,
                    "explanation": "SU/T3 with DSCR <135% (secured): Loan declined."}

    return {"decision": "REQUIREMENT", "confidence": 0.99,
            "explanation": "Debenture and a minimum of 50% personal guarantee (PG) required."}

def evaluate_sme_risk(sme_profile: str, risk_profile: str, dscr: float,
                      loan_amount: float, loan_type: str) -> dict:
    """Evaluate SME risk using global checks and profile-specific rules."""
    # Global Checks (Rules 1 and 70)
    global_result = global_sme_checks(dscr, loan_amount)
    if global_result:
        return global_result

    # Dispatch to the appropriate SME profile evaluator
    if sme_profile == "EB":
        return evaluate_eb_risk(risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "ESB":
        return evaluate_esb_risk(risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "NTB":
        return evaluate_ntb_risk(risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "SU":
        return evaluate_su_risk(risk_profile, dscr, loan_amount, loan_type)
    else:
        return {"decision": "FAIL", "confidence": 0.99,
                "explanation": "Invalid SME profile."}
# ---------------------- UNDERWRITER SCHEMA ----------------------

UNDERWRITER_SCHEMA = {
    "version": "2.0",
    "instructions": {
        "role": "Underwriter GPT",
        "objective": (
            "Generate a detailed explanation for an auto-approved loan application. "
            "Explain in detail the business logic and rules applied to the input scenario data. "
            "Your explanation should be comprehensive, transparent, and structured so that it is both human-readable and machine-loggable."
        ),
        "prompt_guidelines": [
            "Begin with a 'Decisioning Summary' that outlines the final decision and the confidence rating provided by the system.",
            "Include a 'Business Logic Explanation' section where you detail the key rules and calculations that led to the decision, including references to specific rule IDs.",
            "Provide an 'Input Scenario Analysis' section summarizing the input data (e.g., SME profile, risk profile, DSCR, loan amount, loan type).",
            "List any deterministic rules that were triggered during the evaluation and explain their impact on the decision.",
            "Conclude with 'Risk Mitigation Recommendations' if applicable or note if the scenario is borderline and may require further manual review.",
            "Ensure your output is clearly structured with headings for each section and formatted in JSON or YAML."
        ],
        "output_structure": {
            "decisioning_summary": "Overview of the final decision and the associated confidence rating.",
            "business_logic_explanation": "Detailed explanation of the business logic and rules applied, including references to specific rule IDs.",
            "input_scenario_analysis": "Summary of the input scenario data provided.",
            "applied_rules": "A list of triggered rules with their IDs and detailed explanations of their impact on the decision.",
            "risk_recommendations": "Recommendations for mitigating risks or notes on borderline cases that may require manual review."
        }
    },
    "data_sources": {
        "decisioning_gpt": (
            "This is a self-referential process. The same GPT that generates the decision provides the detailed explanation "
            "of the applied business logic based on the input scenario data."
        )
    },
    "fallback": (
        "If any required data from the input scenario is missing or ambiguous, default to flagging the application for manual review. "
        "Include a clear note in your explanation specifying which parts of the input data were incomplete or unclear."
    )
}

def get_underwriter_schema():
    """
    Return the comprehensive underwriter schema containing instructions,
    output structure, data source references, and fallback guidelines.
    """
    return UNDERWRITER_SCHEMA

# ---------------------- FASTAPI APP SETUP ----------------------
app = FastAPI(
    title="Loan Evaluation API",
    description="API for evaluating loan eligibility based on risk profiles, borrower checks, and SME risk rules (Rules 1-70).",
    version="1.0"
)

# Define Pydantic models for the incoming request payloads.
class BorrowerTypeRequest(BaseModel):
    borrower_type: str

class BorrowerIDVerificationRequest(BaseModel):
    is_verified: bool

class OpenBankingRequest(BaseModel):
    is_connected: bool

from pydantic import BaseModel, Field

class SMERiskRequest(BaseModel):
    sme_profile: str = Field(alias="smeProfile")
    risk_profile: str = Field(alias="riskProfile")
    dscr: float = Field(alias="stressedDSCR")
    loan_amount: float = Field(alias="loanAmount")
    loan_type: str = Field(alias="loanType")

# ---------------------- API ENDPOINTS ----------------------
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
        loan_type=request.loan_type
    )
@app.get("/underwriter-schema")
async def underwriter_schema_endpoint():
    return get_underwriter_schema()

# ---------------------- RUN THE APP ----------------------
if __name__ == "__main__":
    # Pass the app instance directly to uvicorn.run so that the file name dependency is removed.
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
