# underwriter.py

import copy
import logging
from datetime import datetime
from typing import Dict, List
from pydantic import BaseModel
from gpt_client import call_gpt

logger = logging.getLogger(__name__)

# -------------------------------
# Underwriter Schema Models and Definition
# -------------------------------
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
    audit_and_versioning: Dict[str, str]
    compliance_notes: str

UNDERWRITER_SCHEMA = {
    "version": "1.0",
    "instructions": {
        "role": "Underwriter GPT",
        "objective": (
            "Generate a detailed, engaging explanation for an auto-approved loan application. "
            "Your explanation should be clear and natural, providing a thorough understanding of the decision-making process, "
            "while faithfully reflecting all the business rules, risk adjustments, and compliance requirements."
        ),
        "prompt_guidelines": [
            "Provide a clear summary of the final decision and its confidence rating.",
            "Explain the key business rules, risk adjustments, and thresholds in plain language.",
            "Describe the input scenario (e.g., SME profile, risk profile, DSCR, loan amount, loan type and industry sector) in a natural manner.",
            "Detail any triggered rules in an accessible, non-formulaic style.",
            "Include a friendly checklist of required documents and verifications.",
            "Include overall risk score, required PG percentage, and any missing documents details from the evaluation.",
            "Offer any additional recommendations for further risk mitigation if applicable.",
            "Conclude with audit details and a brief compliance note."
        ],
        "output_structure": {
            "decisioning_summary": "A natural overview of the final decision and confidence.",
            "business_logic_explanation": "A clear, plain-language explanation of the applied business rules and risk adjustments.",
            "input_scenario_analysis": "A narrative description of the input data with context.",
            "applied_rules": "An accessible account of any triggered rules.",
            "submission_checklist": "A checklist of required documents.",
            "risk_recommendations": "Additional risk mitigation recommendations, if any.",
            "audit_information": "Concise audit details including rule version and timestamp.",
            "compliance_notes": "A brief note confirming adherence to regulatory guidelines."
        }
    },
    "data_sources": {
        "decisioning_gpt": "GPT is used to generate the decision explanation.",
        "external_data": "Credit reports, open banking data, financial statements, and verification records."
    },
    "audit_and_versioning": {
        "rule_version": "1.0",
        "timestamp": "To be updated at evaluation time",
        "audit_trail": "A brief log of input data, applied rules, risk adjustments, and the final decision."
    },
    "compliance_notes": (
        "Ensure the narrative adheres to internal lending policies and regulatory requirements. "
        "Any deviations should be clearly documented."
    )
}

def get_underwriter_schema() -> Dict:
    """
    Returns the underwriter schema with an updated audit timestamp.
    """
    schema = copy.deepcopy(UNDERWRITER_SCHEMA)
    schema["audit_and_versioning"]["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return schema

# -------------------------------
# Prompt Modularization Functions
# -------------------------------

def build_business_logic_section(schema: dict) -> str:
    """
    Constructs the section of the prompt that explains the business logic.
    """
    return (
        f"You are {schema['instructions']['role']}. Your task is to generate an engaging and natural explanation for a loan application decision.\n\n"
        "Please include the following in your narrative:\n"
        "- A friendly and professional summary of the final decision.\n"
        "- An explanation of the key business rules, risk adjustments, and thresholds in plain language.\n"
        "- A descriptive account of the input scenario (e.g., SME profile, risk profile, DSCR, loan amount, loan type, and industry sector).\n"
        "- A clear list of any triggered rules explained in accessible terms.\n"
        "- A checklist of required documents or verifications needed.\n"
        "- Overall evaluation details such as overall risk score, required PG percentage, and any missing documents.\n"
        "- Additional recommendations for mitigating risk.\n"
        "- Audit information (rule version and timestamp) and a short compliance note.\n"
    )

def build_evaluation_details_section(evaluation_decision: dict) -> str:
    """
    Constructs the section with evaluation decision details.
    """
    return (
        f"Evaluation Decision:\n"
        f"  - Decision: {evaluation_decision['decision']}\n"
        f"  - Confidence: {evaluation_decision['confidence']}\n"
        f"  - Explanation: {evaluation_decision['explanation']}\n\n"
        f"Additional Evaluation Details:\n"
        f"  - Overall Risk Score: {evaluation_decision.get('overall_risk', 'N/A')}\n"
        f"  - Required PG Percentage: {evaluation_decision.get('required_pg', 'N/A')}\n"
        f"  - Missing Documents: {evaluation_decision.get('missing_documents', 'None')}\n"
    )

def build_additional_context_section(timestamp: str, request_id: str) -> str:
    """
    Constructs the section with additional contextual data.
    """
    return f"Additional Context: Timestamp: {timestamp}, Request ID: {request_id}\n"

def build_objective_section(schema: dict) -> str:
    """
    Constructs the objective section of the prompt.
    """
    return f"Objective:\n{schema['instructions']['objective']}\n"

# -------------------------------
# Narrative Generation Functions Using Modular Prompts
# -------------------------------

def generate_underwriter_narrative(evaluation_decision: dict) -> str:
    """
    Generate a detailed narrative explanation using modular prompt sections.
    """
    schema = get_underwriter_schema()
    timestamp = schema["audit_and_versioning"]["timestamp"]
    request_id = evaluation_decision.get("request_id", "N/A")
    
    business_logic = build_business_logic_section(schema)
    objective = build_objective_section(schema)
    evaluation_details = build_evaluation_details_section(evaluation_decision)
    additional_context = build_additional_context_section(timestamp, request_id)
    
    prompt = (
        f"{business_logic}\n"
        f"{objective}\n"
        f"{evaluation_details}\n"
        f"{additional_context}\n"
        "Please generate the narrative explanation."
    )
    
    logger.debug(f"Underwriter narrative prompt: {prompt}")
    try:
        narrative = call_gpt(prompt)
        logger.debug(f"Underwriter narrative response: {narrative}")
    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        raise Exception(f"Failed to generate narrative due to GPT API error: {e}")
    return narrative

def check_underwriter_narrative(narrative: str, evaluation_decision: dict) -> str:
    """
    Check the generated narrative for consistency using modular prompt sections.
    """
    schema = get_underwriter_schema()
    timestamp = schema["audit_and_versioning"]["timestamp"]
    request_id = evaluation_decision.get("request_id", "N/A")
    
    evaluation_details = build_evaluation_details_section(evaluation_decision)
    additional_context = build_additional_context_section(timestamp, request_id)
    
    prompt = (
        "Review the following evaluation decision and narrative explanation for consistency with the business rules and risk configurations.\n\n"
        f"{evaluation_details}\n"
        f"{additional_context}\n"
        "Narrative Explanation:\n"
        f"{narrative}\n\n"
        "If the narrative accurately and naturally reflects the evaluation decision and business logic, reply with 'No contradictions found.' "
        "Otherwise, list any inconsistencies."
    )
    
    logger.debug(f"Underwriter narrative check prompt: {prompt}")
    try:
        check_result = call_gpt(prompt)
        logger.debug(f"Underwriter narrative check response: {check_result}")
    except Exception as e:
        logger.error(f"Error checking narrative: {e}")
        raise Exception(f"Failed to check narrative due to GPT API error: {e}")
    return check_result

def generate_and_verify_narrative(evaluation_decision: dict) -> str:
    """
    Generate and verify narrative explanation with up to 3 retries if inconsistencies are found.
    """
    max_retries = 3
    narrative = ""
    for attempt in range(max_retries):
        logger.debug(f"Attempt {attempt+1} for narrative generation.")
        try:
            narrative = generate_underwriter_narrative(evaluation_decision)
            check_result = check_underwriter_narrative(narrative, evaluation_decision)
        except Exception as e:
            logger.error(f"Error during narrative generation/check on attempt {attempt+1}: {e}")
            continue
        if "No contradictions found" in check_result:
            return narrative
        else:
            logger.info(f"Attempt {attempt+1}: discrepancies found - {check_result}. Retrying narrative generation...")
    logger.warning("Max retries reached. Returning last generated narrative despite discrepancies.")
    return narrative
