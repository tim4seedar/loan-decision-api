import os
import logging
import copy
from datetime import datetime
from pydantic import BaseModel
from typing import Dict, List
from gpt_client import call_gpt

# Use call_gpt(...) wherever you need GPT

# --------------------------------------------------
# DECISIONS Definitions
# --------------------------------------------------
DECISIONS = {
    "PROGRESS": {
         "value": "PROGRESS",
         "definition": "The application has met the preliminary criteria and is advanced to the next stage for further evaluation, including documentation and condition checks."
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

#---------------------------------------------------
# Risk Profiles
# --------------------------------------------------
RISK_PROFILES = {
    "T1": {"label": "Low Risk", "missed_payments": (0, 1), "ccjs_defaults": (0, 2500), "iva_liquidation_years": 5, "confidence": 0.95},
    "T2": {"label": "Medium Risk", "missed_payments": (0, 2), "ccjs_defaults": (2500, 3000), "iva_liquidation_years": 5, "confidence": 0.85},
    "T3": {"label": "High Risk", "missed_payments": (3, float('inf')), "ccjs_defaults": (3000, 5000), "iva_liquidation_years": 5, "confidence": 0.70}
}

#---------------------------------------------------
# Industry Sectors
# --------------------------------------------------
ACCEPTABLE_INDUSTRY_SECTORS = [
    "Construction",
    "Professional, Scientific, and Technical Activities",
    "Wholesale and Retail Trade",
    "Other Service Activities",
    "Human Health and Social Work Activities",
    "Information and Communication",
    "Transportation and Storage",
    "Education",
    "Arts, Entertainment, and Recreation",
    "Manufacturing",
    "Accommodation and Food Service Activities",
    "Agriculture, Forestry, and Fishing",
    "Real Estate Activities",
    "Administrative and Support Service Activities",
    "Financial and Insurance Activities"
]
ACCEPTABLE_INDUSTRY_RISK_SCORES = {
    "Construction": 1,
    "Professional, Scientific, and Technical Activities": 1,
    "Wholesale and Retail Trade": 1,
    "Other Service Activities": 1,
    "Human Health and Social Work Activities": 1,
    "Information and Communication": 1,
    "Transportation and Storage": 1,
    "Education": 1,
    "Arts, Entertainment, and Recreation": 1,
    "Manufacturing": 1,
    "Accommodation and Food Service Activities": 1,
    "Agriculture, Forestry and Fishing": 1,
    "Real Estate Activities": 1,
    "Administrative and Support Service Activities": 1,
    "Financial and Insurance Activities": 1
}
FAILED_INDUSTRY_SECTORS = [
    "Illicit or Illegal industries",
    "Places of Worship",
    "Places of Gambling",
    "Environmentally harmful industries",
    "Predatory financial services (e.g. payday lenders)"
]

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
# Confidence Configs
# --------------------------------------------------
CONFIG = {"loan_adjustment_factor": 0.10}

SME_CONFIDENCE_ADJUSTMENTS = {"EB": 0.10, "ESB": 0.00, "NTB": -0.15}
RISK_CONFIDENCE_ADJUSTMENTS = {"T1": 0.10, "T2": 0.00, "T3": -0.15}
DSCR_CONFIDENCE_ADJUSTMENTS = {"low": -0.15, "medium": 0.00, "high": 0.10}
INDUSTRY_CONFIDENCE_ADJUSTMENTS = {
    "Construction": 0.00,
    "Professional, Scientific, and Technical Activities": 0.00,
    "Wholesale and Retail Trade": 0.00,
    "Other Service Activities": 0.00,
    "Human Health and Social Work Activities": 0.00,
    "Information and Communication": 0.00,
    "Transportation and Storage": 0.00,
    "Education": 0.00,
    "Arts, Entertainment, and Recreation": 0.00,
    "Manufacturing": 0.00,
    "Accommodation and Food Service Activities": 0.00,
    "Agriculture, Forestry and Fishing": 0.00,
    "Real Estate Activities": 0.00,
    "Administrative and Support Service Activities": 0.00,
    "Financial and Insurance Activities": 0.00
}

def adjust_confidence(sme_profile: str, requested_loan: float, min_loan: float, max_loan: float,
                      risk_profile: str, dscr_level: str, industry_sector: str) -> float:
    
    base_confidence = SME_PROFILES.get(sme_profile, {}).get("confidence", 0.75)
    sme_adjust = SME_CONFIDENCE_ADJUSTMENTS.get(sme_profile, 0.0)
    base_confidence += sme_adjust

    factor = CONFIG["loan_adjustment_factor"]
    denominator = max_loan - min_loan if max_loan != min_loan else 1
    reduction = ((requested_loan - min_loan) / denominator) * factor
    loan_conf = max(base_confidence - reduction, 0.50)
    risk_conf = loan_conf + RISK_CONFIDENCE_ADJUSTMENTS.get(risk_profile, 0)
    final_conf = risk_conf + DSCR_CONFIDENCE_ADJUSTMENTS.get(dscr_level, 0)
    industry_adjust = INDUSTRY_CONFIDENCE_ADJUSTMENTS.get(industry_sector, 0)
    final_conf += industry_adjust
    return max(min(final_conf, 1.00), 0.50)

# --------------------------------------------------
# Risk Curve Configs
# --------------------------------------------------
# Risk scores for SME profiles
SME_RISK_SCORES = {
    "EB": 1.0,  # lower risk
    "ESB": 1.5,
    "NTB": 2.0,
    "SU": 2.5   # higher risk
}

# Risk scores for DSCR levels
# (assuming that a higher DSCR implies lower risk)
DSCR_RISK_SCORES = {
    "high": 1.0,  # best case: DSCR is high
    "medium": 1.5,
    "low": 2.0    # worst case: DSCR is low (just above minimum)
}

# Risk scores for Credit Risk Profiles
CREDIT_RISK_SCORES = {
    "T1": 1.0,  # best credit tier
    "T2": 1.5,
    "T3": 2.0   # worst credit tier
}

# Risk scores for Industry Sectors (for acceptable sectors)
# You might want to set different scores here from the confidence adjustments.
INDUSTRY_RISK_SCORES = {
    "Construction": 1.0,
    "Professional, Scientific, and Technical Activities": 1.0,
    "Wholesale and Retail Trade": 1.0,
    "Other Service Activities": 1.0,
    "Human Health and Social Work Activities": 1.0,
    "Information and Communication": 1.0,
    "Transportation and Storage": 1.0,
    "Education": 1.0,
    "Arts, Entertainment, and Recreation": 1.0,
    "Manufacturing": 1.0,
    "Accommodation and Food Service Activities": 1.0,
    "Agriculture, Forestry and Fishing": 1.0,
    "Real Estate Activities": 1.0,
    "Administrative and Support Service Activities": 1.0,
    "Financial and Insurance Activities": 1.0
}      
# Define weights for each risk factor (they should add up to 1.0 if you want a normalized score)
WEIGHT_SME = 0.32
WEIGHT_DSCR = 0.32
WEIGHT_CREDIT = 0.32
WEIGHT_INDUSTRY = 0.04

def calculate_overall_risk(sme_profile: str, dscr_level: str, credit_profile: str, industry_sector: str) -> float:
    """
    Calculates an overall risk score by applying weights to the risk scores of each factor.
    Lower overall scores indicate lower risk.
    """
    # Retrieve individual risk scores (using default values if a key isn't found)
    sme_score = SME_RISK_SCORES.get(sme_profile, 2.0)
    dscr_score = DSCR_RISK_SCORES.get(dscr_level, 2.0)
    credit_score = CREDIT_RISK_SCORES.get(credit_profile, 2.0)
    industry_score = INDUSTRY_RISK_SCORES.get(industry_sector, 2.0)
    
    overall_risk = (WEIGHT_SME * sme_score +
                    WEIGHT_DSCR * dscr_score +
                    WEIGHT_CREDIT * credit_score +
                    WEIGHT_INDUSTRY * industry_score)
    return overall_risk

# -------------------------------------------------------------------
# Global Checks and Borrower Types   
# -------------------------------------------------------------------
# Optionally define configurable thresholds
MIN_DSCR = 1.25
MIN_LOAN_AMOUNT = 25001

def evaluate_borrower_type(borrower_type: str) -> dict:
    allowed = {"LTD", "Sole Trader", "LLP"}
    if borrower_type in allowed:
        return {
            "decision": DECISIONS["PROGRESS"]["value"],
            "confidence": 0.95,
            "explanation": f"Borrower type {borrower_type} is accepted."
        }
    return {
        "decision": DECISIONS["FAIL"]["value"],
        "confidence": 0.99,
        "explanation": f"Borrower type {borrower_type} is not allowed."
    }

def global_sme_checks(dscr: float, loan_amount: float, risk_profile: str, sme_profile: str, industry_sector: str) -> dict:
    if dscr < MIN_DSCR:
        return {"decision": DECISIONS["FAIL"]["value"], "confidence": 0.99, "explanation": f"DSCR < {MIN_DSCR * 100:.0f}%. Loan declined."}
    if loan_amount < MIN_LOAN_AMOUNT:
        return {"decision": DECISIONS["FAIL"]["value"], "confidence": 0.99, "explanation": f"Loan amount below £{MIN_LOAN_AMOUNT}. Does not meet minimum threshold."}
    if risk_profile == "T3":
        return {"decision": DECISIONS["FAIL"]["value"], "confidence": 0.99, "explanation": "T3 risk profiles do not meet the minimum credit profile threshold."}
    if sme_profile == "SU":
        return {"decision": DECISIONS["FAIL"]["value"], "confidence": 0.99, "explanation": "Startups are not considered for the Happy Path."}
    if industry_sector in FAILED_INDUSTRY_SECTORS:
        return {"decision": DECISIONS["FAIL"]["value"],
                "confidence": 0.99,
                "explanation": f"Industry sector '{industry_sector}' is not accepted."}
    if industry_sector not in ACCEPTABLE_INDUSTRY_SECTORS:
        return {"decision": DECISIONS["FLAG/UW"]["value"],
                "confidence": 0.99,
                "explanation": f"Industry sector '{industry_sector}' is not recognized."}
    return {}

# -------------------------------------------------------------------
# Conditions Checklist
# -------------------------------------------------------------------
REQUIRED_DOCUMENTS = {
    "common": {
        "Completed Application Form": "Must capture the loan request, purpose, trading history, and full details of the borrower and directors—including both personal and business assets/liabilities and a declaration of credit history.",
        "Proof of Identity": "For all business owners, directors, and persons with significant control. Acceptable forms include: Passport, Driving license, National identity card, or other government-issued photo ID.",
        "Proof of Address": "Certified proof of address, such as a recent utility bill (not older than 3 months), bank statement, or local authority tax bill.",
        "Bank Statements": "A minimum of 6 months of business bank statements and at least 3 months of personal bank statements for the business owner or directors.",
        "Declaration of Income and Expenditure": "A formal declaration outlining the borrower’s income, expenditures, and overall financial position.",
        "Credit History Documentation": "Evidence of credit history, such as a credit report or related documentation from a credit reference agency.",
        "Valuation and Professional Reports": "For secured loans, an independent professional valuation report of the collateral is required.",
        "Agreement in Principle": "An agreement in principle may be required as part of the overall documentation package.",
        "Legal Representation/Independent Legal Advice": "Documentation confirming independent legal advice or representation if required."
    },
    "EB": {
        "Financial Statements": "Either 3 years of historical accounts OR 2 years of historical accounts and 1 year of projections."
    },
    "ESB": {
        "Financial Statements": "1 year of historical accounts and 2 years of projections."
    },
    "NTB": {
        "Financial Statements": "Up to 12 months of historical accounts and, for the current year, the remaining period projections plus 2 additional years of projections."
    },
    "SU": {
        "Financial Statements": "3 years of projections."
    }
}

# Personal Guarantee (PG) Definitions
PG_BASE_PERCENTAGE = 0.20  # Base PG requirement for the lowest risk borrowers
PG_MAX_PERCENTAGE = 1.00   # Maximum PG requirement for the highest risk borrowers

CONDITIONS_CHECKLIST = {
    "Required Conditions": {
        "Personal Guarantee": {
            "description": "A personal guarantee is required for all applications except for Sole Traders.",
            "base_requirement": PG_BASE_PERCENTAGE,
            "note": "The required PG percentage may be adjusted upward based on the overall risk score from the risk curve. Sole Traders are exempt."
        },
        "Debenture": {
            "description": "A debenture covering appropriate assets is required for all applications except for Sole Traders.",
            "note": "This condition is waived for Sole Traders."
        },
        "Borrower ID Verification": {
            "description": "Borrower ID must be verified for all applications.",
            "note": "This is a required condition for all borrowers. Documentation must be provided if verification is not automatic."
        },
        "Open Banking": {
            "description": "Open banking connectivity must be established for all applications.",
            "note": "This is a required condition for all borrowers. Documentation must be provided if connectivity cannot be confirmed."
        }
    }
}

# -------------------------------------------------------------------
# PG Scaling
# -------------------------------------------------------------------
def determine_pg_percentage(overall_risk: float) -> float:
    # Define the risk range (calibrate these values as needed)
    min_risk = 1.0
    max_risk = 2.0

    # Base PG for lowest risk
    base_pg = 0.20  # 20%
    # Maximum PG you might require for the highest risk
    max_pg = 1.00   # 100%
    
    # Normalize the risk score between 0 and 1
    normalized_risk = (overall_risk - min_risk) / (max_risk - min_risk)
    
    # Linearly interpolate between base and max PG percentages
    pg_percentage = base_pg + normalized_risk * (max_pg - base_pg)
    
    return pg_percentage
