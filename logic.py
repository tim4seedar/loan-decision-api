import os
import logging
import copy
from datetime import datetime
from pydantic import BaseModel
from typing import List
from config import (
    DECISIONS,
    MIN_DSCR,
    MIN_LOAN_AMOUNT,
    REQUIRED_DOCUMENTS,
    calculate_overall_risk,
    determine_pg_percentage
)
from config import adjust_confidence
from config import evaluate_borrower_type
from config import SME_PROFILES  # for base confidence
from config import EvaluationError
import logging

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Business Logic (i.e. Rules)
# --------------------------------------------------

# Below is a simplified version of the business logic which is categorized by SME profile

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
     
    # Check against the minimum allowed DSCR
    if dscr < MIN_DSCR:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"DSCR of {dscr} is below the minimum allowed DSCR of {MIN_DSCR}. Loan declined."
        }
        logger.info(f"EB Evaluation DSCR hard stop: {decision}")
        return decision

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
    if risk_profile == "T1" and dscr >= 1.25:
        if loan_type == "unsecured" and loan_amount <= 150000:
            decision = {"decision": "PROGRESS", "confidence": 0.87,
                        "explanation": "EB/T1 with DSCR >125% qualifies for an unsecured loan up to £150,000."}
            logger.info(f"EB Evaluation (T1, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 250000:
            decision = {"decision": "PROGRESS", "confidence": 0.89,
                        "explanation": "EB/T1 with DSCR >150% qualifies for a secured loan."}
            logger.info(f"EB Evaluation (T1, secured): {decision}")
            return decision
    if risk_profile == "T2" and dscr >= 1.25:
        if loan_type == "unsecured" and loan_amount <= 150000:
            decision = {"decision": "PROGRESS", "confidence": 0.77,
                        "explanation": "EB/T2 with DSCR >125% qualifies for an unsecured loan up to £150,000."}
            logger.info(f"EB Evaluation (T2, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 250000:
            decision = {"decision": "PROGRESS", "confidence": 0.89,
                        "explanation": "EB/T2 with DSCR >150% qualifies for a secured loan."}
            logger.info(f"EB Evaluation (T2, secured): {decision}")
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

    # Check against the minimum allowed DSCR
    if dscr < MIN_DSCR:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"DSCR of {dscr} is below the minimum allowed DSCR of {MIN_DSCR}. Loan declined."
        }
        logger.info(f"ESB Evaluation DSCR hard stop: {decision}")
        return decision

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
    if risk_profile == "T1" and dscr >= 1.25:
        if loan_type == "unsecured" and loan_amount <= 80000:
            decision = {"decision": "PROGRESS", "confidence": 0.88,
                        "explanation": "ESB/T1 with DSCR >125% qualifies for an unsecured loan."}
            logger.info(f"ESB Evaluation (T1, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PROGRESS", "confidence": 0.88,
                        "explanation": "ESB/T1 with DSCR >125% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T1, secured): {decision}")
            return decision
    if risk_profile == "T2" and dscr >= 1.25:
        if loan_type == "unsecured" and loan_amount <= 80000:
            decision = {"decision": "PROGRESS", "confidence": 0.88,
                        "explanation": "ESB/T2 with DSCR >125% qualifies for an unsecured loan."}
            logger.info(f"ESB Evaluation (T1, unsecured): {decision}")
            return decision
        if loan_type == "secured" and loan_amount <= 150000:
            decision = {"decision": "PROGRESS", "confidence": 0.88,
                        "explanation": "ESB/T2 with DSCR >125% qualifies for a secured loan."}
            logger.info(f"ESB Evaluation (T2, secured): {decision}")
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

    # Check against the minimum allowed DSCR
    if dscr < MIN_DSCR:
        decision = {
            "decision": "FAIL",
            "confidence": 0.99,
            "explanation": f"DSCR of {dscr} is below the minimum allowed DSCR of {MIN_DSCR}. Loan declined."
        }
        logger.info(f"NTB Evaluation DSCR hard stop: {decision}")
        return decision

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
    if risk_profile == "T1" and dscr >= 1.25:
        if loan_type == "unsecured" and loan_amount <= 60000:
            decision = {
                "decision": "PROGRESS",
                "confidence": 0.80,
                "explanation": "NTB/T1 with DSCR >125% qualifies for an unsecured loan."
            }
            logger.info(f"NTB Evaluation (T1, unsecured): {decision}")
            return decision
        if loan_type == "secured" and dscr > 1.25 and loan_amount <= 100000:
            decision = {
                "decision": "PROGRESS",
                "confidence": 0.85,
                "explanation": "NTB/T1 with DSCR >150% qualifies for a secured loan."
            }
            logger.info(f"NTB Evaluation (T1, secured): {decision}")
            return decision
    if risk_profile == "T2" and dscr >= 1.25:
        if loan_type == "unsecured" and loan_amount <= 60000:
            decision = {
                "decision": "PROGRESS",
                "confidence": 0.80,
                "explanation": "NTB/T2 with DSCR >125% qualifies for an unsecured loan."
            }
            logger.info(f"NTB Evaluation (T2, unsecured): {decision}")
            return decision
        if loan_type == "secured" and dscr > 1.25 and loan_amount <= 100000:
            decision = {
                "decision": "PROGRESS",
                "confidence": 0.85,
                "explanation": "NTB/T2 with DSCR >150% qualifies for a secured loan."
            }
            logger.info(f"NTB Evaluation (T2, secured): {decision}")
            return decision

# --------------------------------------------------
# Final Outcome
# --------------------------------------------------
def finalize_conditional_pass(decision: dict, provided_docs: List[str], sme_profile: str) -> dict:
    """
    Updates a decision that was previously marked "PROGRESS" by checking the required documents.
    If any required documents (merged from common and SME-specific) are missing, they are attached
    to the decision and the outcome is set to CONDITIONAL_PASS.
    """
    # Merge common and SME-specific required documents
    required_docs = REQUIRED_DOCUMENTS.get("common", {}).copy()
    # Use SME profile as key if present (e.g., "EB", "ESB", "NTB", "SU")
    if sme_profile in REQUIRED_DOCUMENTS:
        required_docs.update(REQUIRED_DOCUMENTS.get(sme_profile, {}))
    
    missing_docs = {}
    for doc, description in required_docs.items():
        if doc not in provided_docs:
            missing_docs[doc] = description

    # Update the decision outcome to CONDITIONAL_PASS and attach missing documents.
    decision["decision"] = DECISIONS["CONDITIONAL_PASS"]["value"]
    decision["missing_documents"] = missing_docs
    decision["explanation"] += " Conditional approval pending submission of required documents."
    return decision

def evaluate_application(
    sme_profile: str,
    risk_profile: str,
    dscr: float,
    loan_amount: float,
    loan_type: str,
    industry_sector: str,
    provided_docs: List[str]
) -> dict:
    """
    Evaluate an application by:
      1. Checking global criteria.
      2. Running the appropriate risk evaluation function.
      3. Generating a required documents checklist.
      4. Converting a "PROGRESS" outcome to "CONDITIONAL_PASS" with missing documents.
    
    Note: If DSCR or other financial metrics are updated in a subsequent API call,
    the outcome may change (e.g., to FAIL if DSCR falls below the threshold).
    """
    # Global Checks (these could be expanded as needed)
    if dscr < MIN_DSCR:
        decision = {
            "decision": DECISIONS["FAIL"]["value"],
            "confidence": 0.99,
            "explanation": f"DSCR of {dscr} is below the minimum threshold of {MIN_DSCR}. Loan declined."
        }
        logger.info(f"Global check failure: {decision}")
        return decision

    if loan_amount < MIN_LOAN_AMOUNT:
        decision = {
            "decision": DECISIONS["FAIL"]["value"],
            "confidence": 0.99,
            "explanation": f"Loan amount £{loan_amount} is below the minimum threshold of £{MIN_LOAN_AMOUNT}."
        }
        logger.info(f"Global check failure: {decision}")
        return decision

    # Call the appropriate risk evaluation function based on SME profile.
    # (Assuming that evaluate_eb_risk, evaluate_esb_risk, and evaluate_ntb_risk are defined.)
    if sme_profile == "EB":
        decision = evaluate_eb_risk(sme_profile, risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "ESB":
        decision = evaluate_esb_risk(sme_profile, risk_profile, dscr, loan_amount, loan_type)
    elif sme_profile == "NTB":
        decision = evaluate_ntb_risk(sme_profile, risk_profile, dscr, loan_amount, loan_type)
    else:
        # For other profiles (or Startups if not handled elsewhere), return FAIL
        decision = {
            "decision": DECISIONS["FAIL"]["value"],
            "confidence": 0.99,
            "explanation": f"SME profile '{sme_profile}' is not supported for the Happy Path."
        }
        logger.info(f"SME profile failure: {decision}")
        return decision

    # At this point, the risk evaluation function returned "PROGRESS" for eligible scenarios.
    # Now integrate the required documents checklist.
    if decision["decision"] == DECISIONS["PROGRESS"]["value"]:
        decision = finalize_conditional_pass(decision, provided_docs, sme_profile)

    # Optionally, you could calculate overall risk and adjust conditions further (e.g., PG percentage).
    overall_risk = calculate_overall_risk(sme_profile, 
                                           # Here you might need to determine dscr_level externally
                                           dscr_level=get_dscr_level(dscr),  
                                           credit_profile=risk_profile, 
                                           industry_sector=industry_sector)
    decision["overall_risk"] = overall_risk
    decision["required_pg"] = determine_pg_percentage(overall_risk)
    
    return decision

def get_dscr_level(dscr: float) -> str:
    """
    Helper function to categorize DSCR into 'high', 'medium', or 'low'.
    Thresholds can be adjusted based on your business rules.
    """
    if dscr >= 1.5:
        return "high"
    elif dscr >= 1.35:
        return "medium"
    else:
        return "low"
