"""
Base Agent — shared logic for all specialist agents.
Every specialist agent (logic, security, style, test) inherits from this.
"""
import os
from typing import List, Dict
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

# One LLM instance shared across all agents
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.1  # low temperature = consistent, focused reviews (not creative)
)


def build_context_block(similar_chunks: List[Dict]) -> str:
    """
    Convert similar past chunks into a readable context block
    that gets appended to every agent's prompt.
    """
    if not similar_chunks:
        return "No similar past code found in history."

    lines = ["SIMILAR PAST CODE FROM PREVIOUS PRs:"]
    for i, chunk in enumerate(similar_chunks, 1):
        lines.append(f"\n[Past Example {i}] File: {chunk['file_path']} (similarity: {chunk['similarity']})")
        lines.append(chunk['content'][:300])  # cap at 300 chars to save tokens
    return "\n".join(lines)


def parse_llm_response(response_text: str) -> Dict:
    """
    Parse LLM response into structured comment + confidence score.
    LLM is prompted to respond in a specific format — we extract fields here.

    Expected format from LLM:
    ISSUE: <description>
    CONFIDENCE: <0.0-1.0>
    FAILURE_TYPE: <engineering|llm_uncertain>
    SUGGESTION: <fix>
    """
    lines = response_text.strip().split("\n")
    result = {
        "comment": response_text,  # fallback — full response if parsing fails
        "confidence_score": 0.5,
        "failure_type": "llm_uncertain"
    }

    for line in lines:
        if line.startswith("ISSUE:"):
            result["comment"] = line.replace("ISSUE:", "").strip()
        elif line.startswith("CONFIDENCE:"):
            try:
                score = float(line.replace("CONFIDENCE:", "").strip())
                result["confidence_score"] = max(0.0, min(1.0, score))  # clamp 0-1
            except ValueError:
                pass
        elif line.startswith("FAILURE_TYPE:"):
            ft = line.replace("FAILURE_TYPE:", "").strip().lower()
            if ft in ["engineering", "llm_uncertain"]:
                result["failure_type"] = ft
        elif line.startswith("SUGGESTION:"):
            result["comment"] += "\n💡 " + line.replace("SUGGESTION:", "").strip()

    return result


def run_agent(
    agent_name: str,
    system_prompt: str,
    chunk: Dict,
    review_run_id: int
) -> List[Dict]:
    """
    Core agent runner — used by all 4 specialist agents.
    Takes a chunk, builds prompt with context, calls LLM, returns structured comments.
    """
    context_block = build_context_block(chunk.get("similar_past_chunks", []))

    human_message = f"""
FILE: {chunk['file_path']}

DIFF/CODE TO REVIEW:
{chunk['content']}

{context_block}

Review the above code from your specialist perspective.
For EACH issue found, respond in this EXACT format:

ISSUE: <clear description of the problem>
CONFIDENCE: <float between 0.0 and 1.0>
FAILURE_TYPE: <engineering if it's a definite code bug/issue, llm_uncertain if you're not sure>
SUGGESTION: <specific fix or recommendation>

If no issues found, respond with:
ISSUE: No issues found
CONFIDENCE: 1.0
FAILURE_TYPE: engineering
SUGGESTION: None
"""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_message)
    ])

    parsed = parse_llm_response(response.content)

    return {
        "agent_name": agent_name,
        "file_path": chunk["file_path"],
        "comment": parsed["comment"],
        "confidence_score": parsed["confidence_score"],
        "failure_type": parsed["failure_type"],
        "review_run_id": review_run_id,
        "status": "pending"
    }