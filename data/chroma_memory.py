"""
chroma_memory.py — Agent Memory using ChromaDB
Agents store lessons and successful patterns here.
On each cycle, similar past situations are retrieved as context.
"""

import os
import json
from datetime import datetime, timezone
from loguru import logger

CHROMA_URL = os.getenv("CHROMA_URL", "http://localhost:8001")
COLLECTION  = "agent_memories"


def _get_client():
    import chromadb
    return chromadb.HttpClient(host="localhost", port=8001)


def _get_collection():
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )


async def store_memory(
    agent_name: str,
    signal: str,
    correct: bool,
    market_conditions: dict,
    lesson: str,
    trade_result: str | None = None,
) -> None:
    """
    Store a lesson from a completed trade.

    Args:
        agent_name:        Which agent is storing this memory
        signal:            The signal the agent gave (BULLISH/BEARISH/NEUTRAL)
        correct:           Whether the signal was correct
        market_conditions: Dict of conditions at signal time (fear_greed, funding, etc.)
        lesson:            Natural language lesson derived from this trade
        trade_result:      "tp" | "sl" | "manual"
    """
    try:
        collection = _get_collection()
        doc_id = f"{agent_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        doc = (
            f"Agent: {agent_name} | Signal: {signal} | Correct: {correct} | "
            f"Result: {trade_result} | Conditions: {json.dumps(market_conditions)} | "
            f"Lesson: {lesson}"
        )
        metadata = {
            "agent":    agent_name,
            "signal":   signal,
            "correct":  correct,
            "result":   trade_result or "unknown",
            "ts":       datetime.now(timezone.utc).isoformat(),
            **{k: str(v) for k, v in market_conditions.items()},
        }
        collection.add(documents=[doc], metadatas=[metadata], ids=[doc_id])
        logger.debug(f"[MEMORY] Stored memory for {agent_name}: {lesson[:60]}...")
    except Exception as e:
        logger.warning(f"[MEMORY] ChromaDB store failed: {e}")

async def store_human_feedback(agent_name: str, feedback: str) -> None:
    """
    Store direct human feedback / chat logs for an agent.
    """
    try:
        collection = _get_collection()
        doc_id = f"{agent_name}_human_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        doc = f"Agent: {agent_name} | Human Feedback: {feedback}"
        metadata = {
            "agent": agent_name,
            "signal": "HUMAN_OVERRIDE",
            "correct": True,
            "result": "manual",
            "ts": datetime.now(timezone.utc).isoformat(),
            "lesson": feedback
        }
        collection.add(documents=[doc], metadatas=[metadata], ids=[doc_id])
        logger.info(f"[MEMORY] Stored human feedback for {agent_name}: {feedback[:50]}...")
    except Exception as e:
        logger.warning(f"[MEMORY] ChromaDB feedback store failed: {e}")


async def recall_similar(
    agent_name: str,
    current_conditions: dict,
    n_results: int = 3,
) -> list[dict]:
    """
    Retrieve similar past situations for an agent.

    Args:
        agent_name:          Agent requesting memories
        current_conditions:  Current market state dict
        n_results:           Number of similar memories to return

    Returns:
        List of memory dicts with lesson, signal, correct, result
    """
    try:
        collection = _get_collection()
        query = (
            f"Agent: {agent_name} | "
            f"Conditions: {json.dumps(current_conditions, default=str)}"
        )
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"agent": agent_name},
        )
        memories = []
        if results and results["documents"]:
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                memories.append({
                    "lesson":  meta.get("lesson", doc),
                    "signal":  meta.get("signal"),
                    "correct": meta.get("correct"),
                    "result":  meta.get("result"),
                    "ts":      meta.get("ts"),
                })
        logger.debug(f"[MEMORY] Recalled {len(memories)} memories for {agent_name}")
        return memories
    except Exception as e:
        logger.warning(f"[MEMORY] ChromaDB recall failed: {e}")
        return []


def format_memories_for_prompt(memories: list[dict]) -> str:
    """Format memories into a prompt-ready string."""
    if not memories:
        return ""
    lines = ["📚 Relevant past experiences:"]
    for m in memories:
        tick = "✅" if m.get("correct") else "❌"
        lines.append(
            f"  {tick} {m.get('signal')} signal → {m.get('result', '?')} | lesson: {m.get('lesson', '')}"
        )
    return "\n".join(lines)
