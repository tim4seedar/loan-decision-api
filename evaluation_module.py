import os
import logging
import copy
from datetime import datetime
from pydantic import BaseModel
from typing import Dict, List
from gpt_client import call_gpt

# Use call_gpt(...) wherever you need GPT
# test note for commit and push


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
            "Include a 'Business Logic Explanation' section detailing all key rules, risk adjustments, and calculations applied. Do not imply that a DSCR of 1.5x is strictly required; rather note that while a DSCR of 1.5x is ideal, any DSCR above 1.25x is considered acceptable, with borderline cases (e.g. DSCR around 1.35x) warranting additional review.",
            "Provide an 'Input Scenario Analysis' section summarizing the complete input data, including SME profile, risk profile, stressed DSCR, loan amount, loan type, borrower type, credit checks, and verification statuses.",
            "Enumerate any triggered deterministic rules along with detailed explanations of how they impacted the decision.",
            "For secured loans, explicitly include an analysis of collateral details. This should cover: verifying that the property is of an acceptable type; checking that a recent valuation report is available and has been analyzed; determining whether any legal charges already exist on the property; assessing the feasibility of obtaining a second charge if necessary; confirming that the property value is sufficient to service the loan; and calculating the Loan-to-Value (LTV) ratio to ensure it falls within Seedar's exposure appetite.",
            "If any collateral details (such as property type, valuation report, existing legal charges, feasibility of a second charge, or LTV ratio) are not provided or are incomplete, explicitly note the missing information and request that the applicant supply the necessary documentation for a full evaluation.",
            "Include 'Risk Mitigation Recommendations' outlining any additional security measures or manual review requirements for borderline cases.",
            "Add an 'Audit Information' section that records the rule version, evaluation timestamp, and a log of the decision-making process.",
            "Include 'Compliance Notes' that describe adherence to regulatory guidelines and internal lending policies, along with any documented exceptions."
        ],
        "output_structure": {
    "decisioning_summary": "A concise overview of the final decision and the associated confidence rating.",
    "decision_in_principle": "A preliminary decision template that outlines the conditions for full approval, including any contingencies.",
    "business_logic_explanation": "A detailed breakdown of the applied business rules, risk adjustments, and calculations, including references to specific rule IDs.",
    "input_scenario_analysis": "A summary of all provided input data used in the evaluation.",
    "applied_rules": "A list of triggered deterministic rules with their IDs and detailed explanations of how they impacted the decision.",
    "submission_checklist": "A checklist of the documents required from the borrower to progress the full application (e.g., Personal Guarantee, Debenture documentation, ID verification, AML/KYC records, collateral documentation, etc.).",
    "risk_recommendations": "Recommendations for mitigating risks, including additional security measures or notes for manual review if the case is borderline.",
    "audit_information": "Metadata including the rule version, evaluation timestamp, and an audit trail of all decisions made.",
    "compliance_notes": "Notes confirming adherence to regulatory requirements and internal lending policies, along with any documented exceptions."
	}
    },
   "data_sources": {
    "decisioning_gpt": "This process is self-referential; the same GPT that generates the decision is used to provide a detailed explanation of the applied business logic using the input scenario data.",
    "external_data": "Includes verifications from external sources such as credit bureaus, open banking data, financial statements, and borrower identity checks."
},
    "fallback": (
    "If any required data from the input scenario is missing, ambiguous, or fails verification, the system should return a CONDITIONAL_PASS decision. "
    "In these cases, the underwriter must explicitly document which data points are incomplete or uncertain, and clearly outline the conditions that must be met—such as sufficient Personal Guarantees, debentures, and completed AML/KYC checks—for final approval. "
    "This approach ensures that while the application passes automated checks conditionally, final approval is contingent upon fulfilling these specific security and verification requirements, rather than necessitating a full manual review."
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
    schema = copy.deepcopy(UNDERWRITER_SCHEMA)
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
# Configuration
# --------------------------------------------------
CONFIG = {"loan_adjustment_factor": 0.10}

RISK_PROFILES = {
    "T1": {"label": "Low Risk", "missed_payments": (0, 1), "ccjs_defaults": (0, 2500), "iva_liquidation_years": 5, "confidence": 0.95},
    "T2": {"label": "Medium Risk", "missed_payments": (0, 2), "ccjs_defaults": (2500, 3000), "iva_liquidation_years": 5, "confidence": 0.85},
    "T3": {"label": "High Risk", "missed_payments": (3, float('inf')), "ccjs_defaults": (3000, 5000), "iva_liquidation_years": 5, "confidence": 0.70}
}

RISK_CONFIDENCE_ADJUSTMENTS = {"T1": 0.10, "T2": 0.00, "T3": -0.15}
DSCR_CONFIDENCE_ADJUSTMENTS = {"low": -0.15, "medium": 0.00, "high": 0.10}

# --------------------------------------------------
# Business Logic (i.e. Rules)
# --------------------------------------------------
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
# --------------------------------------------------
# Underwriter Helper Function
# --------------------------------------------------
def generate_underwriter_narrative(evaluation_decision: dict) -> str:
    """
    Generate a narrative explanation for an evaluation decision.
    
    This function builds a prompt by embedding the evaluation decision details
    into the underwriter schema and then calls the GPT engine to generate the narrative.
    """
    # Retrieve the underwriter schema from the module
    schema = get_underwriter_schema()

    # Build the prompt using the evaluation decision with additional sections
    prompt = f"""
You are {schema['instructions']['role']}.
Objective: {schema['instructions']['objective']}

Using the evaluation decision provided below, generate a detailed narrative explanation that includes the following sections:

1. Decision in Principle:
   - Provide a clear preliminary decision that outlines the final decision outcome (e.g., PASS, CONDITIONAL_PASS, FLAG/AI, FLAG/UW, FAIL) and details any conditions that must be met before full approval. Clearly articulate any contingencies or conditions that apply.

2. Business Logic Explanation:
   - Describe in detail the key business rules, risk adjustments, and numerical thresholds that influenced this decision. Reference specific rule IDs, risk metrics, and relevant thresholds where applicable.

3. Input Scenario Analysis:
   - Summarize the complete input data used in this evaluation, including the SME profile, risk profile, stressed DSCR, loan amount, loan type, and any borrower verification or credit check statuses.

4. Submission Checklist:
   - List all required documents and verifications that the broker/borrower must provide to progress the full application. This should include items such as Personal Guarantee documentation, Debenture or legal charge confirmation, ID verification, AML/KYC records, and collateral or property valuation details.

5. Risk Mitigation Recommendations:
   - Outline any additional measures or further reviews required (e.g., enhanced due diligence, additional security measures) particularly for borderline cases.

6. Audit Information:
   - Include metadata such as the rule version, the evaluation timestamp, and a brief audit trail summarizing the decision-making process.

7. Compliance Notes:
   - Confirm that the decision aligns with internal lending policies and external regulatory guidelines, noting any exceptions or additional requirements if applicable.

Evaluation Decision:
  - Decision: {evaluation_decision['decision']}
  - Confidence: {evaluation_decision['confidence']}
  - Explanation: {evaluation_decision['explanation']}

Based on the above, generate a detailed narrative explanation that:
  • Starts with a Decisioning Summary.
  • Details the business logic and key rules that led to this outcome (referencing rule IDs if applicable).
  • Summarizes the relevant input scenario.
  
Generate the narrative explanation using nuanced and professional language. Do not add any interpretations beyond what is provided in the evaluation decision.
    """
    try:
        narrative = call_gpt(prompt)  # GPT API Call
    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        raise EvaluationError(f"Failed to generate narrative due to GPT API error: {e}")
    
    return narrative

# --------------------------------------------------
# Check You Work Function
# --------------------------------------------------
def check_underwriter_narrative(narrative: str, evaluation_decision: dict) -> str:
    """
    Check the generated narrative for any inconsistencies or contradictions 
    with the evaluation decision and underlying business logic.
    
    This function builds a prompt for GPT to review the narrative against the 
    evaluation decision details. If no contradictions are found, it should return 
    a message indicating "No contradictions found." Otherwise, it should list the discrepancies.
    """
    schema = get_underwriter_schema()
    prompt = f"""
Review the following evaluation decision details and the narrative explanation. 
Your task is to ensure that the narrative does not contradict or conflict with the underlying business logic.
    
Evaluation Decision:
  - Decision: {evaluation_decision['decision']}
  - Confidence: {evaluation_decision['confidence']}
  - Explanation: {evaluation_decision['explanation']}

Narrative Explanation:
{narrative}

If the narrative is consistent with the evaluation decision and does not contain any contradictions with the business logic, reply with "No contradictions found." 
If there are discrepancies, please list them clearly.
    """
    try:
        check_result = call_gpt(prompt)  # Call the GPT API to perform the check
    except Exception as e:
        logger.error(f"Error checking narrative: {e}")
        # You might choose to either raise an error or return a default response
        raise EvaluationError(f"Failed to check narrative due to GPT API error: {e}")
    
    return check_result

# --------------------------------------------------
# Check You Work Function
# --------------------------------------------------
def generate_and_verify_narrative(evaluation_decision: dict) -> str:
    """
    Generate a narrative explanation for an evaluation decision and automatically check for contradictions.
    
    This function builds a prompt by embedding the evaluation decision details into the underwriter schema,
    calls the GPT engine to generate the narrative, then uses a secondary prompt to verify the narrative against
    the underlying business logic. If any contradictions are found, it will automatically attempt to regenerate
    the narrative.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            narrative = generate_underwriter_narrative(evaluation_decision)
        except EvaluationError as e:
            logger.error(f"Error during narrative generation on attempt {attempt+1}: {e}")
            continue  # Retry the narrative generation
        
        try:
            check_result = check_underwriter_narrative(narrative, evaluation_decision)
        except EvaluationError as e:
            logger.error(f"Error during narrative check on attempt {attempt+1}: {e}")
            continue  # Retry the narrative generation
        
        if "No contradictions found" in check_result:
            return narrative
        else:
            logger.info(f"Check attempt {attempt+1}: discrepancies found - {check_result}. Regenerating narrative...")
    
    logger.warning("Max retries reached. Returning last generated narrative despite discrepancies.")
    return narrative
