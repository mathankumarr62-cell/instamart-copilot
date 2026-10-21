"""ReAct refund agent with iteration, token and time limits, checkpoints and resume (tasks 6-8)."""
import json
import logging
import time

from instamart import config
from instamart.llm_backend import chat
from instamart.part_d import checkpoint
from instamart.part_d.tools import TOOLS_SPEC, current_run_id, execute_tool

log = logging.getLogger(__name__)

SYSTEM_PROMPT = ("You are the Instamart refund AGENT. Use the tools to look up the order, check the refund "
                 "policy, calculate the refund, then issue it or escalate it above INR 1000. Finish with one "
                 "line 'STATUS: reason' where STATUS is REFUND, ESCALATE, DENIED or NOT_FOUND.")
FALLBACK_MAX_ITERATIONS = "FALLBACK_MAX_ITERATIONS"
FALLBACK_TOKEN_LIMIT = "FALLBACK_TOKEN_LIMIT"
FALLBACK_TIMEOUT = "FALLBACK_TIMEOUT"
REFUND_TOOLS = ("calculate_refund", "issue_refund", "escalate_to_human")


class SimulatedCrash(RuntimeError):
    """Raised on purpose after a checkpoint to demonstrate resume_agent."""


def new_state(user_message: str, scenario_id: str, run_id: str) -> dict:
    """Initial agent state: system + user messages and empty counters."""
    return {"run_id": run_id, "scenario_id": scenario_id,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message}],
            "tokens_used": 0, "llm_calls": 0, "step": 0, "tools_executed": [], "steps": []}


def status_of(final_answer: str) -> str:
    """The word before the colon of the final answer, e.g. 'REFUND: INR 128.25 issued.' -> REFUND."""
    return final_answer.split(":", 1)[0].strip() if ":" in final_answer else "UNKNOWN"


def refund_amount(steps: list[dict]) -> float:
    """Refund in INR from the last refund-related observation (0 when none)."""
    for step in reversed(steps):
        if step["tool"] in REFUND_TOOLS and "refund_inr" in step["observation"]:
            return float(step["observation"]["refund_inr"])
    return 0.0


def _result(state: dict, status: str, final_answer: str) -> dict:
    """Assemble the dictionary returned by run_agent / resume_agent."""
    return {"run_id": state["run_id"], "scenario_id": state["scenario_id"], "status": status,
            "final_answer": final_answer, "steps": state["steps"], "llm_calls": state["llm_calls"],
            "tokens_used": state["tokens_used"], "tools_executed": list(state["tools_executed"]),
            "refund_inr": refund_amount(state["steps"]) if status in ("REFUND", "ESCALATE") else 0.0}


def _fallback(state: dict, status: str, reason: str) -> dict:
    """Stop safely and hand over to a human with a short summary of what was done."""
    tools = ", ".join(state["tools_executed"]) or "none"
    summary = (f"Handed to a human: {reason} after {state['llm_calls']} model calls and "
               f"{state['tokens_used']} tokens. Tools run: {tools}. Request: {state['messages'][1]['content']}")
    log.warning("run %s stopped with %s", state["run_id"], status)
    return _result(state, status, summary)


def _execute(state: dict, tool_call, crash_after_tools: int | None) -> None:
    """Run one requested tool, append its observation, checkpoint, and optionally simulate a crash."""
    observation = execute_tool(tool_call.name, tool_call.arguments)
    state["messages"].append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_call.name,
                              "content": json.dumps(observation)})
    state["steps"].append({"tool": tool_call.name, "arguments": tool_call.arguments, "observation": observation})
    state["tools_executed"].append(tool_call.name)
    state["step"] += 1
    checkpoint.save(state)
    if crash_after_tools is not None and len(state["tools_executed"]) == crash_after_tools:
        raise SimulatedCrash(f"simulated crash after tool {crash_after_tools} ({tool_call.name})")


def _loop(state: dict, max_iterations: int, token_limit: int, time_limit_seconds: float,
          crash_after_tools: int | None = None) -> dict:
    """The ReAct loop shared by run_agent and resume_agent."""
    start = time.monotonic()
    token = current_run_id.set(state["run_id"])
    try:
        while True:
            if time.monotonic() - start >= time_limit_seconds:
                return _fallback(state, FALLBACK_TIMEOUT, f"time limit of {time_limit_seconds} s reached")
            if state["llm_calls"] >= max_iterations:
                return _fallback(state, FALLBACK_MAX_ITERATIONS, f"iteration limit of {max_iterations} reached without a final answer")
            response = chat(state["messages"], tools=TOOLS_SPEC)
            state["llm_calls"] += 1
            state["tokens_used"] += response.usage.total_tokens
            if state["tokens_used"] > token_limit:
                return _fallback(state, FALLBACK_TOKEN_LIMIT, f"token limit of {token_limit} exceeded")
            message = response.choices[0].message
            if not message.tool_calls:
                return _result(state, status_of(message.content or ""), message.content or "")
            state["messages"].append({"role": "assistant", "content": None, "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in message.tool_calls]})
            for tool_call in message.tool_calls:
                _execute(state, tool_call, crash_after_tools)
    finally:
        current_run_id.reset(token)


def run_agent(user_message: str, scenario_id: str, max_iterations: int = config.AGENT_MAX_ITERATIONS,
              token_limit: int = config.AGENT_TOKEN_LIMIT, time_limit_seconds: float = config.AGENT_TIME_LIMIT_SECONDS,
              run_id: str | None = None, crash_after_tools: int | None = None) -> dict:
    """Run the refund agent on one request; returns status, final_answer, steps, llm_calls, tokens_used."""
    state = new_state(user_message, scenario_id, run_id or scenario_id)
    return _loop(state, max_iterations, token_limit, time_limit_seconds, crash_after_tools)


def resume_agent(run_id: str, max_iterations: int = config.AGENT_MAX_ITERATIONS,
                 token_limit: int = config.AGENT_TOKEN_LIMIT,
                 time_limit_seconds: float = config.AGENT_TIME_LIMIT_SECONDS) -> dict:
    """Continue a run from state/<run_id>.json; model-call and token counters carry over, the clock restarts."""
    state = checkpoint.load(run_id)
    log.info("resuming %s after %d tools: %s", run_id, state["step"], state["tools_executed"])
    return _loop(state, max_iterations, token_limit, time_limit_seconds)
