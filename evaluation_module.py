import os
import logging
from datetime import datetime
from pydantic import BaseModel
from typing import Dict, List

# --------------------------------------------------
# DECISIONS Definitions
# --------------------------------------------------
DECISIONS = {
    "PASS": {
        "value": "PASS",
        "definition": "The application is approved without any conditions."
    },
    "FAIL": {
        "value": "FAIL",
        "definition": "The application is declined."
    },
    "CONDITIONAL_PASS": {
        "value": "CONDITIONAL_PASS",
        "definition": "The application is approved on condition that certain requirements are met."
    },
    "FLAG_AI": {
        "value": "FLAG/AI",
        "definition": "The application requires an AI review."
    },
    "FLAG_UW": {
        "value": "FLAG/UW",
        "definition": "The application requires an underwriter review."
    }
}
#---------------------------------------------------
# Error Logging
# --------------------------------------------------
# Configure structured logging
logging.basicConfig(
    level=logging.INFO,  # You can adjust the log level (DEBUG, INFO, WARNING, ERROR)
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

class EvaluationError(Exception):
    """Custom exception for errors during loan evaluation."""
    pass

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
            "Begin with a 'Decisioning Summary' that states the final decision (PASS, FLAG/AI, FLAG/UW, FAIL, or CONDITIONAL_PASS) and the overall confidence rating.",
            "Include a 'Business Logic Explanation' section detailing all key rules, risk adjustments, and calculations applied. Reference specific rule IDs and thresholds where applicable.",
            "Provide an 'Input Scenario Analysis' section summarizing the complete input data, including SME profile, risk profile, DSCR, loan amount, loan type, borrower type, credit checks, and verification statuses.",
            "Enumerate any triggered deterministic rules along with detailed explanations of their impact on the decision.",
            "Include 'Risk Mitigation Recommendations' outlining any additional security measures or manual review requirements for borderline cases.",
            "Add an 'Audit Information' section that records the rule version, evaluation timestamp, and a log of the decision-making process.",
            "Include 'Compliance Notes' that describe adherence to regulatory guidelines and internal lending policies, along with any documented exceptions."
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
# SME_PROFILES Dictionary
# --------------------------------------------------
SME_PROFILES = {
    "EB": {
        "label": "Established Business",
        "confidence": 0.95,
        "loan_unsecured": {
            "min": 25000,  # current value
            "max": 150000  # current value
        },
        "loan_secured": {
            "min": 25000,  # current value
            "max": 250000  # current value
        },
        "financials_required": ["3 years certified accounts", "2 years accounts + 12-month forecast"]
    },
    "ESB": {
        "label": "Early-Stage Business",
        "confidence": 0.85,
        "loan_unsecured": {
            "min": 25000,  # current value
            "max": 75000   # current value
        },
        "loan_secured": {
            "min": 25000,  # current value
            "max": 150000  # current value
        },
        "financials_required": ["1 year certified accounts", "12+ months management accounts"]
    },
    "NTB": {
        "label": "Newly Trading Business",
        "confidence": 0.75,
        "loan_unsecured": {
            "min": 25000,  # current value
            "max": 60000   # current value
        },
        "loan_secured": {
            "min": 25000,  # current value
            "max": 100000  # current value
        },
        "financials_required": ["3-11 months management accounts"]
    },
    "SU": {
        "label": "Startup",
        "confidence": 0.60,
        "loan_unsecured": {
            "min": 26000,  # current value
            "max": 40000   # current value
        },
        "loan_secured": {
            "min": 26000,  # current value
            "max": 80000   # current value
        },
        "financials_required": ["No management accounts, pre-revenue"]
    }
}
# --------------------------------------------------
# Configuration & Business Logic
# --------------------------------------------------
CONFIG = {"loan_adjustment_factor": 0.10}

RISK_PROFILES = {
    "T1": {"label": "Low Risk", "missed_payments": (0, 1), "ccjs_defaults": (0, 2500), "iva_liquidation_years": 5, "confidence": 0.95},
    "T2": {"label": "Medium Risk", "missed_payments": (0, 2), "ccjs_defaults": (2500, 3000), "iva_liquidation_years": 5, "confidence": 0.85},
    "T3": {"label": "High Risk", "missed_payments": (3, float('inf')), "ccjs_defaults": (3000, 5000), "iva_liquidation_years": 5, "confidence": 0.70}
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
    return {"decision": "CONDITIONAL_PASS", "confidence": 0.99,
            "explanation": "Loan approved on condition that borrower provides valid ID verification before funding."}

def evaluate_open_banking(is_connected: bool) -> dict:
    if is_connected:
        return {"decision": "PASS", "confidence": 0.95,
                "explanation": "Open banking is connected."}
    return {"decision": "CONDITIONAL_PASS", "confidence": 0.99,
            "explanation": "Loan approved on condition that the borrower successfully connects Open Banking before funding."}

def global_sme_checks(dscr: float, loan_amount: float) -> dict:
    if dscr < 1.25:
        return {"decision": "FAIL", "confidence": 0.99, "explanation": "DSCR <125%. Loan declined."}
    if loan_amount < 25001:
        return {"decision": "FAIL", "confidence": 0.99, "explanation": "Loan amount below £25,001. Does not meet minimum threshold."}
    return {}

# --------------------------------------------------
# EB Evaluations
# --------------------------------------------------
def evaluate_eb_risk(sme_profile: str, risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    """
    Evaluate the loan eligibility for an Established Business (EB) SME.
    This version enforces all hardcoded numeric limits (minimum and maximum borrowing limits)
    before processing DSCR and risk profile conditions.
    """
    if sme_profile != "EB":
        error_msg = f"evaluate_eb_risk can only evaluate EB profiles. Received: {sme_profile}"
        logger.error(error_msg)
        raise EvaluationError(error_msg)

    # Enforce hardcoded borrowing limits for EB
    if loan_type.lower() == "secured":
        min_limit = SME_PROFILES["EB"]["loan_secured"]["min"]
        max_limit = SME_PROFILES["EB"]["loan_secured"]["max"]
    else:
        min_limit = SME_PROFILES["EB"]["loan_unsecured"]["min"]
        max_limit = SME_PROFILES["EB"]["loan_unsecured"]["max"]

    # Check against the minimum allowed loan amount
    if loan_amount < min_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"Loan amount £{loan_amount} is below the minimum allowed limit of £{min_limit} for EB {loan_type} loans."
        }
        logger.info(f"EB Evaluation hard stop (min limit): {decision}")
        return decision

    # Check against the maximum allowed loan amount
    if loan_amount > max_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"Loan amount £{loan_amount} exceeds the maximum allowed limit of £{max_limit} for EB {loan_type} loans."
        }
        logger.info(f"EB Evaluation hard stop (max limit): {decision}")
        return decision

    base_conf = SME_PROFILES["EB"]["confidence"]
    if risk_profile == "T2" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.87,
                        "explanation": "EB/T2 with DSCR >150% qualifies for an unsecured loan."}
            logger.info(f"EB Evaluation (T2, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 250000:
            decision = {"decision": "PASS", "confidence": 0.89,
                        "explanation": "EB/T2 with DSCR >150% qualifies for a secured loan."}
            logger.info(f"EB Evaluation (T2, secured): {decision}")
            return decision

    if risk_profile == "T3" and dscr >= 1.50:
        if loan_type == "unsecured" and loan_amount <= 100000:
            decision = {"decision": "FLAG/AI", "confidence": 0.75,
                        "explanation": "EB/T3 with DSCR >150% (unsecured): AI review required."}
            logger.info(f"EB Evaluation (T3, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 250000:
            decision = {"decision": "FLAG/AI", "confidence": 0.78,
                        "explanation": "EB/T3 with DSCR >150% (secured): AI review required."}
            logger.info(f"EB Evaluation (T3, secured): {decision}")
            return decision

    if risk_profile == "T1" and 1.349 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.85,
                        "explanation": "EB/T1 with DSCR just below 150% qualifies for an unsecured loan."}
            logger.info(f"EB Evaluation (T1, just below 150%, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 250000:
            decision = {"decision": "PASS", "confidence": 0.88,
                        "explanation": "EB/T1 with DSCR just below 150% qualifies for a secured loan."}
            logger.info(f"EB Evaluation (T1, just below 150%, secured): {decision}")
            return decision

    if 1.349 < dscr <= 1.50:
        if risk_profile == "T2":
            if loan_type == "unsecured" and loan_amount <= 100000:
                decision = {"decision": "PASS", "confidence": 0.80,
                            "explanation": "EB/T2 with DSCR just below 150% qualifies for an unsecured loan."}
                logger.info(f"EB Evaluation (T2, just below 150%, unsecured): {decision}")
                return decision
            if loan_type == "secured" and loan_amount <= 250000:
                decision = {"decision": "PASS", "confidence": 0.83,
                            "explanation": "EB/T2 with DSCR just below 150% qualifies for a secured loan."}
                logger.info(f"EB Evaluation (T2, just below 150%, secured): {decision}")
                return decision
        if risk_profile == "T3":
            if loan_type == "unsecured" and loan_amount <= 75000:
                decision = {"decision": "FLAG/UW", "confidence": 0.70,
                            "explanation": "EB/T3 with DSCR just below 150%: underwriter review required (unsecured)."}
                logger.info(f"EB Evaluation (T3, just below 150%, unsecured): {decision}")
                return decision
            if loan_type == "secured" and loan_amount <= 250000:
                decision = {"decision": "FLAG/UW", "confidence": 0.72,
                            "explanation": "EB/T3 with DSCR just below 150%: underwriter review required (secured)."}
                logger.info(f"EB Evaluation (T3, just below 150%, secured): {decision}")
                return decision

    if 1.25 < dscr <= 1.35:
        if risk_profile == "T1":
            if loan_type == "unsecured" and loan_amount <= 100000:
                decision = {"decision": "PASS", "confidence": 0.78,
                            "explanation": "EB/T1 with DSCR between 125%-135% qualifies for an unsecured loan."}
                logger.info(f"EB Evaluation (T1, 1.25<DSCR<=1.35, unsecured): {decision}")
                return decision
            if loan_type == "secured" and loan_amount <= 250000:
                decision = {"decision": "PASS", "confidence": 0.82,
                            "explanation": "EB/T1 with DSCR between 125%-135% qualifies for a secured loan."}
                logger.info(f"EB Evaluation (T1, 1.25<DSCR<=1.35, secured): {decision}")
                return decision
        if risk_profile == "T2":
            if loan_type == "unsecured" and loan_amount <= 75000:
                decision = {"decision": "PASS", "confidence": 0.75,
                            "explanation": "EB/T2 with DSCR between 125%-135% qualifies for an unsecured loan."}
                logger.info(f"EB Evaluation (T2, 1.25<DSCR<=1.35, unsecured): {decision}")
                return decision
            if loan_type == "secured" and loan_amount <= 250000:
                decision = {"decision": "PASS", "confidence": 0.79,
                            "explanation": "EB/T2 with DSCR between 125%-135% qualifies for a secured loan."}
                logger.info(f"EB Evaluation (T2, 1.25<DSCR<=1.35, secured): {decision}")
                return decision
        if risk_profile == "T3":
            if loan_type == "unsecured" and loan_amount <= 50000:
                decision = {"decision": "FLAG/AI", "confidence": 0.65,
                            "explanation": "EB/T3 with DSCR between 125%-135%: AI review required (unsecured)."}
                logger.info(f"EB Evaluation (T3, 1.25<DSCR<=1.35, unsecured): {decision}")
                return decision
            if loan_type == "secured" and loan_amount <= 250000:
                decision = {"decision": "FLAG/UW", "confidence": 0.70,
                            "explanation": "EB/T3 with DSCR between 125%-135%: underwriter review required (secured)."}
                logger.info(f"EB Evaluation (T3, 1.25<DSCR<=1.35, secured): {decision}")
                return decision

    # Comprehensive fallback for cases missing only additional checks (PG, Debenture, ID, AML/KYC):
    fallback_explanation = (
        "Although the loan amount complies with the defined borrowing limits, "
        "the applicant’s DSCR and risk indicators do not justify an automatic PASS. "
        "However, since the only issues relate to missing personal guarantees, debentures, ID verifications, or AML/KYC checks, "
        "the application is granted a CONDITIONAL_PASS subject to these additional conditions."
    )
    decision = {"decision": "CONDITIONAL_PASS", "confidence": 0.99, "explanation": fallback_explanation}
    logger.info(f"EB Evaluation comprehensive fallback: {decision}")
    return decision

# --------------------------------------------------
# ESB Evaluations
# --------------------------------------------------
def evaluate_esb_risk(sme_profile: str, risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    """
    Evaluate the loan eligibility for an Early-Stage Business (ESB) SME.
    This version enforces all hardcoded numeric limits (minimum and maximum borrowing limits)
    before processing DSCR and risk profile conditions.
    """
    if sme_profile != "ESB":
        error_msg = f"evaluate_esb_risk can only evaluate ESB profiles. Received: {sme_profile}"
        logger.error(error_msg)
        raise EvaluationError(error_msg)

    # Enforce hardcoded borrowing limits from the SME_PROFILES configuration.
    # Both minimum and maximum limits must be met.
    if loan_type.lower() == "secured":
        min_limit = SME_PROFILES["ESB"]["loan_secured"]["min"]
        max_limit = SME_PROFILES["ESB"]["loan_secured"]["max"]
    else:
        min_limit = SME_PROFILES["ESB"]["loan_unsecured"]["min"]
        max_limit = SME_PROFILES["ESB"]["loan_unsecured"]["max"]

    # Check against the minimum allowed loan amount
    if loan_amount < min_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": (f"Loan amount £{loan_amount} is below the minimum allowed limit of £{min_limit} "
                            f"for ESB {loan_type} loans.")
        }
        logger.info(f"ESB Evaluation hard stop (min limit): {decision}")
        return decision

    # Check against the maximum allowed loan amount
    if loan_amount > max_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": (f"Loan amount £{loan_amount} exceeds the maximum allowed limit of £{max_limit} "
                            f"for ESB {loan_type} loans.")
        }
        logger.info(f"ESB Evaluation hard stop (max limit): {decision}")
        return decision
    base_conf = SME_PROFILES["ESB"]["confidence"]
    if risk_profile == "T1" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 80000:
            decision = {"decision": "PASS", "confidence": 0.88,
                        "explanation": "ESB/T1 with DSCR >150% qualifies for an unsecured loan."}
            logger.info(f"ESB Evaluation (T1, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.90,
                        "explanation": "ESB/T1 with DSCR >150% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T1, secured): {decision}")
            return decision

    if risk_profile == "T2" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 75000:
            decision = {"decision": "PASS", "confidence": 0.85,
                        "explanation": "ESB/T2 with DSCR >150% qualifies for an unsecured loan."}
            logger.info(f"ESB Evaluation (T2, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.87,
                        "explanation": "ESB/T2 with DSCR >150% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T2, secured): {decision}")
            return decision

    if risk_profile == "T3" and dscr > 1.50:
        if loan_type == "unsecured" and loan_amount <= 60000:
            decision = {"decision": "FLAG/AI", "confidence": 0.70,
                        "explanation": "ESB/T3 with DSCR >150% (unsecured): AI review required."}
            logger.info(f"ESB Evaluation (T3, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "FLAG/UW", "confidence": 0.72,
                        "explanation": "ESB/T3 with DSCR >150% (secured): underwriter review required."}
            logger.info(f"ESB Evaluation (T3, secured): {decision}")
            return decision

    if risk_profile == "T1" and 1.35 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 80000:
            decision = {"decision": "PASS", "confidence": 0.85,
                        "explanation": "ESB/T1 with DSCR between 135%-150% qualifies for an unsecured loan."}
            logger.info(f"ESB Evaluation (T1, 1.35<DSCR<=1.50, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.87,
                        "explanation": "ESB/T1 with DSCR between 135%-150% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T1, 1.35<DSCR<=1.50, secured): {decision}")
            return decision

    if risk_profile == "T2" and 1.35 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 75000:
            decision = {"decision": "PASS", "confidence": 0.82,
                        "explanation": "ESB/T2 with DSCR between 135%-150% qualifies for an unsecured loan."}
            logger.info(f"ESB Evaluation (T2, 1.35<DSCR<=1.50, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.85,
                        "explanation": "ESB/T2 with DSCR between 135%-150% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T2, 1.35<DSCR<=1.50, secured): {decision}")
            return decision

    if risk_profile == "T3" and 1.349 < dscr <= 1.50:
        if loan_type == "unsecured" and loan_amount <= 50000:
            decision = {"decision": "FLAG/AI", "confidence": 0.70,
                        "explanation": "ESB/T3 with DSCR between 135%-150%: AI review required (unsecured)."}
            logger.info(f"ESB Evaluation (T3, 1.349<DSCR<=1.50, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "FLAG/UW", "confidence": 0.72,
                        "explanation": "ESB/T3 with DSCR between 135%-150%: underwriter review required (secured)."}
            logger.info(f"ESB Evaluation (T3, 1.349<DSCR<=1.50, secured): {decision}")
            return decision

    if risk_profile == "T1" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            decision = {"decision": "PASS", "confidence": 0.80,
                        "explanation": "ESB/T1 with DSCR between 125%-135% qualifies for an unsecured loan."}
            logger.info(f"ESB Evaluation (T1, 1.25<DSCR<=1.35, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.83,
                        "explanation": "ESB/T1 with DSCR between 125%-135% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T1, 1.25<DSCR<=1.35, secured): {decision}")
            return decision

    if risk_profile == "T2" and 1.25 < dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 50000:
            decision = {"decision": "PASS", "confidence": 0.75,
                        "explanation": "ESB/T2 with DSCR >125% and <135% qualifies for a unsecured loan."}
            logger.info(f"ESB Evaluation (T2, 1.25<DSCR<1.35, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PASS", "confidence": 0.78,
                        "explanation": "ESB/T2 with DSCR >125% and <135% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T2, 1.25<DSCR<1.35, secured): {decision}")
            return decision

    if risk_profile == "T3" and 1.25 < dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            decision = {"decision": "FLAG/AI", "confidence": 0.70,
                        "explanation": "ESB/T3 with DSCR >125% and <135%: AI review required (unsecured)."}
            logger.info(f"ESB Evaluation (T3, 1.25<DSCR<1.35, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "FLAG/UW", "confidence": 0.72,
                        "explanation": "ESB/T3 with DSCR >125% and <135%: underwriter review required (secured)."}
            logger.info(f"ESB Evaluation (T3, 1.25<DSCR<1.35, secured): {decision}")
            return decision

    # Comprehensive fallback for cases missing only additional checks (PG, Debenture, ID, AML/KYC):
    fallback_explanation = (
        "Although the loan amount complies with the defined borrowing limits, "
        "the applicant’s DSCR and risk indicators do not justify an automatic PASS. "
        "However, since the only issues relate to missing personal guarantees, debentures, ID verifications, or AML/KYC checks, "
        "the application is granted a CONDITIONAL_PASS subject to these additional conditions."
    )
    decision = {"decision": "CONDITIONAL_PASS", "confidence": 0.99, "explanation": fallback_explanation}
    logger.info(f"ESB Evaluation comprehensive fallback: {decision}")
    return decision

# --------------------------------------------------
# NTB Evaluations
# --------------------------------------------------
def evaluate_ntb_risk(sme_profile: str, risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    """
    Evaluate the loan eligibility for a Newly Trading Business (NTB) SME.
    This version enforces all hardcoded numeric limits (minimum and maximum borrowing limits)
    before processing DSCR and risk profile conditions.
    """
    if sme_profile != "NTB":
        error_msg = f"evaluate_ntb_risk can only evaluate NTB profiles. Received: {sme_profile}"
        logger.error(error_msg)
        raise EvaluationError(error_msg)

    # Enforce hardcoded borrowing limits for NTB
    if loan_type.lower() == "secured":
        min_limit = SME_PROFILES["NTB"]["loan_secured"]["min"]
        max_limit = SME_PROFILES["NTB"]["loan_secured"]["max"]
    else:
        min_limit = SME_PROFILES["NTB"]["loan_unsecured"]["min"]
        max_limit = SME_PROFILES["NTB"]["loan_unsecured"]["max"]

    # Check against the minimum allowed loan amount
    if loan_amount < min_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"Loan amount £{loan_amount} is below the minimum allowed limit of £{min_limit} for NTB {loan_type} loans."
        }
        logger.info(f"NTB Evaluation hard stop (min limit): {decision}")
        return decision

    # Check against the maximum allowed loan amount
    if loan_amount > max_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"Loan amount £{loan_amount} exceeds the maximum allowed limit of £{max_limit} for NTB {loan_type} loans."
        }
        logger.info(f"NTB Evaluation hard stop (max limit): {decision}")
        return decision

    base_conf = SME_PROFILES["NTB"]["confidence"]    
    if risk_profile == "T1" and dscr > 1.25:
        if loan_type == "unsecured" and loan_amount <= 60000:
            decision = {
                "decision": "PASS",
                "confidence": 0.80,
                "explanation": "NTB/T1 with DSCR >125% qualifies for an unsecured loan."
            }
            logger.info(f"NTB Evaluation (T1, unsecured): {decision}")
            return decision
        if loan_type == "secured" and dscr > 1.50 and loan_amount <= 100000:
            decision = {
                "decision": "PASS",
                "confidence": 0.85,
                "explanation": "NTB/T1 with DSCR >150% qualifies for a secured loan."
            }
            logger.info(f"NTB Evaluation (T1, secured): {decision}")
            return decision

    if risk_profile == "T2" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            decision = {
                "decision": "PASS",
                "confidence": 0.78,
                "explanation": "NTB/T2 with DSCR >135% qualifies for an unsecured loan."
            }
            logger.info(f"NTB Evaluation (T2, unsecured): {decision}")
            return decision
        if loan_type == "secured" and dscr > 1.50 and loan_amount <= 100000:
            decision = {
                "decision": "PASS",
                "confidence": 0.80,
                "explanation": "NTB/T2 with DSCR >150% qualifies for a secured loan."
            }
            logger.info(f"NTB Evaluation (T2, secured): {decision}")
            return decision

    if risk_profile == "T3" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 60000:
            decision = {
                "decision": "FLAG/AI",
                "confidence": 0.70,
                "explanation": "NTB/T3 with DSCR >135%: AI review required (unsecured)."
            }
            logger.info(f"NTB Evaluation (T3, unsecured): {decision}")
            return decision
        if loan_type == "secured" and dscr > 1.25 and loan_amount <= 150000:
            decision = {
                "decision": "FLAG/UW",
                "confidence": 0.72,
                "explanation": "NTB/T3 with DSCR >125%: underwriter review required (secured)."
            }
            logger.info(f"NTB Evaluation (T3, secured): {decision}")
            return decision

    if risk_profile == "T3" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            decision = {
                "decision": "FLAG/AI",
                "confidence": 0.70,
                "explanation": "NTB/T3 with DSCR between 125%-135%: AI review required (unsecured)."
            }
            logger.info(f"NTB Evaluation (T3, unsecured, DSCR 1.25-1.35): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {
                "decision": "FLAG/UW",
                "confidence": 0.72,
                "explanation": "NTB/T3 with DSCR between 125%-135%: underwriter review required (secured)."
            }
            logger.info(f"NTB Evaluation (T3, secured, DSCR 1.25-1.35): {decision}")
            return decision

    # Comprehensive fallback for cases missing only additional checks (PG, Debenture, ID, AML/KYC):
    fallback_explanation = (
        "Although the loan amount complies with the defined borrowing limits, "
        "the applicant’s DSCR and risk indicators do not justify an automatic PASS. "
        "However, since the only issues relate to missing personal guarantees, debentures, ID verifications, or AML/KYC checks, "
        "the application is granted a CONDITIONAL_PASS subject to these additional conditions."
    )
    decision = {"decision": "CONDITIONAL_PASS", "confidence": 0.99, "explanation": fallback_explanation}
    logger.info(f"NTB Evaluation comprehensive fallback: {decision}")
    return decision

# --------------------------------------------------
# SU Evaluations
# --------------------------------------------------
def evaluate_SU_risk(sme_profile: str, risk_profile: str, dscr: float, loan_amount: float, loan_type: str) -> dict:
    """
    Evaluate the loan eligibility for a Startup (SU) SME.
    This version enforces all hardcoded numeric limits (minimum and maximum borrowing limits)
    before processing DSCR and risk profile conditions.
    """
    if sme_profile != "SU":
        error_msg = f"evaluate_SU_risk can only evaluate SU profiles. Received: {sme_profile}"
        logger.error(error_msg)
        raise EvaluationError(error_msg)

    # Enforce hardcoded borrowing limits for SU
    if loan_type.lower() == "secured":
        min_limit = SME_PROFILES["SU"]["loan_secured"]["min"]
        max_limit = SME_PROFILES["SU"]["loan_secured"]["max"]
    else:
        min_limit = SME_PROFILES["SU"]["loan_unsecured"]["min"]
        max_limit = SME_PROFILES["SU"]["loan_unsecured"]["max"]

    # Check against the minimum allowed loan amount
    if loan_amount < min_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"Loan amount £{loan_amount} is below the minimum allowed limit of £{min_limit} for SU {loan_type} loans."
        }
        logger.info(f"SU Evaluation hard stop (min limit): {decision}")
        return decision

    # Check against the maximum allowed loan amount
    if loan_amount > max_limit:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"Loan amount £{loan_amount} exceeds the maximum allowed limit of £{max_limit} for SU {loan_type} loans."
        }
        logger.info(f"SU Evaluation hard stop (max limit): {decision}")
        return decision

    base_conf = SME_PROFILES["SU"]["confidence"]
    if risk_profile == "T2" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            decision = {
                "decision": "FLAG/AI",
                "confidence": 0.72,
                "explanation": "SU/T2 with DSCR >135%: AI review required (unsecured)."
            }
            logger.info(f"SU Evaluation (T2, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 80000:
            decision = {
                "decision": "FLAG/AI",
                "confidence": 0.75,
                "explanation": "SU/T2 with DSCR >135%: AI review required (secured)."
            }
            logger.info(f"SU Evaluation (T2, secured): {decision}")
            return decision

    if risk_profile == "T3" and dscr > 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            decision = {
                "decision": "FLAG/UW",
                "confidence": 0.70,
                "explanation": "SU/T3 with DSCR >135%: underwriter review required (unsecured)."
            }
            logger.info(f"SU Evaluation (T3, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 80000:
            decision = {
                "decision": "FLAG/UW",
                "confidence": 0.73,
                "explanation": "SU/T3 with DSCR >135%: underwriter review required (secured)."
            }
            logger.info(f"SU Evaluation (T3, secured): {decision}")
            return decision

    if risk_profile == "T1" and 1.25 < dscr <= 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            decision = {
                "decision": "FLAG/AI",
                "confidence": 0.70,
                "explanation": "SU/T1 with DSCR between 125%-135%: AI review required (unsecured)."
            }
            logger.info(f"SU Evaluation (T1, unsecured, DSCR 1.25-1.35): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 80000:
            decision = {
                "decision": "FLAG/AI",
                "confidence": 0.73,
                "explanation": "SU/T1 with DSCR between 125%-135%: AI review required (secured)."
            }
            logger.info(f"SU Evaluation (T1, secured, DSCR 1.25-1.35): {decision}")
            return decision

    if risk_profile == "T2" and dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 40000:
            decision = {
                "decision": "FAIL",
                "confidence": 0.99,
                "explanation": "SU/T2 with DSCR <135% (unsecured): Loan declined."
            }
            logger.info(f"SU Evaluation (T2, unsecured, DSCR <1.35): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 80000:
            decision = {
                "decision": "FAIL",
                "confidence": 0.99,
                "explanation": "SU/T2 with DSCR <135% (secured): Loan declined."
            }
            logger.info(f"SU Evaluation (T2, secured, DSCR <1.35): {decision}")
            return decision

    if risk_profile == "T3" and dscr < 1.35:
        if loan_type == "unsecured" and loan_amount <= 26000:
            decision = {
                "decision": "FAIL",
                "confidence": 0.99,
                "explanation": "SU/T3 with DSCR <135% (unsecured): Loan declined."
            }
            logger.info(f"SU Evaluation (T3, unsecured, DSCR <1.35): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 80000:
            decision = {
                "decision": "FAIL",
                "confidence": 0.99,
                "explanation": "SU/T3 with DSCR <135% (secured): Loan declined."
            }
            logger.info(f"SU Evaluation (T3, secured, DSCR <1.35): {decision}")
            return decision

    # Comprehensive fallback for cases missing only additional checks (PG, Debenture, ID, AML/KYC):
    fallback_explanation = (
        "Although the loan amount complies with the defined borrowing limits, "
        "the applicant’s DSCR and risk indicators do not justify an automatic PASS. "
        "However, since the only issues relate to missing personal guarantees, debentures, ID verifications, or AML/KYC checks, "
        "the application is granted a CONDITIONAL_PASS subject to these additional conditions."
    )
    decision = {"decision": "CONDITIONAL_PASS", "confidence": 0.99, "explanation": fallback_explanation}
    logger.info(f"SU Evaluation comprehensive fallback: {decision}")
    return decision

def evaluate_sme_risk(sme_profile: str, risk_profile: str, dscr: float, loan_amount: float, loan_type: str,
                      provided_pg: float, min_pg_required: float, requires_debenture: bool, has_debenture: bool,
                      has_legal_charge: bool, is_due_diligence_complete: bool, is_business_registered: bool) -> dict:
    global_result = global_sme_checks(dscr, loan_amount)
    if global_result:
        logger.info(f"Global SME check failed: {global_result}")
        return global_result

    if sme_profile in ["SU", "NTB", "ESB"] and provided_pg < min_pg_required:
        decision = {
            "decision": "CONDITIONAL_PASS",
            "confidence": 0.99,
            "explanation": f"Loan approved on condition that a minimum {int(min_pg_required * 100)}% Personal Guarantee (PG) is signed before funding."
        }
        logger.info(f"Conditional PG check triggered: {decision}")
        return decision

    if sme_profile in ["NTB", "ESB", "EB"] and requires_debenture and not has_debenture:
        decision = {
            "decision": "CONDITIONAL_PASS",
            "confidence": 0.99,
            "explanation": "Loan approved on condition that a Debenture is signed before funding."
        }
        logger.info(f"Debenture requirement check triggered: {decision}")
        return decision

    if loan_type == "secured" and not has_legal_charge:
        decision = {
            "decision": "CONDITIONAL_PASS",
            "confidence": 0.99,
            "explanation": "Loan approved on condition that the lender obtains a Legal Charge (First or Second) over the security before funding."
        }
        logger.info(f"Legal charge check triggered: {decision}")
        return decision

    if not is_due_diligence_complete:
        decision = {
            "decision": "CONDITIONAL_PASS",
            "confidence": 0.99,
            "explanation": "Loan approved on condition that all AML/KYC and Due Diligence checks are successfully completed before funding."
        }
        logger.info(f"Due diligence check triggered: {decision}")
        return decision

    if not is_business_registered:
        decision = {
            "decision": "CONDITIONAL_PASS",
            "confidence": 0.99,
            "explanation": "Loan approved on condition that borrower provides proof of business registration before funding."
        }
        logger.info(f"Business registration check triggered: {decision}")
        return decision

    if sme_profile == "EB":
        decision = evaluate_eb_risk(sme_profile, risk_profile, dscr, loan_amount, loan_type)
        logger.info(f"EB evaluation returned: {decision}")
        return decision
    elif sme_profile == "ESB":
        decision = evaluate_esb_risk(sme_profile, risk_profile, dscr, loan_amount, loan_type)
        logger.info(f"ESB evaluation returned: {decision}")
        return decision
    elif sme_profile == "NTB":
        decision = evaluate_ntb_risk(sme_profile, risk_profile, dscr, loan_amount, loan_type)
        logger.info(f"NTB evaluation returned: {decision}")
        return decision
    elif sme_profile == "SU":
        decision = evaluate_SU_risk(sme_profile, risk_profile, dscr, loan_amount, loan_type)
        logger.info(f"SU evaluation returned: {decision}")
        return decision
    else:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": "Invalid SME profile."
        }
        logger.error(f"Invalid SME profile provided: {sme_profile}")
        return decision
