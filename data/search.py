"""
search.py — Web Search for News & Sentiment
Providers:
  - Tavily:      AI-optimised search, returns clean summaries (best for LLMs)
  - Brave Search: privacy-respecting web search, broader coverage
"""

import asyncio
import os

import aiohttp
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")
BRAVE_KEY  = os.getenv("BRAVE_SEARCH_API_KEY", "")

TAVILY_BASE = "https://api.tavily.com/search"
BRAVE_BASE  = "https://api.search.brave.com/res/v1/web/search"


# ── Tavily ────────────────────────────────────────────────

async def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Tavily AI search — returns clean summaries ideal for LLM consumption.
    Returns list of {title, url, content, score}.
    """
    if not TAVILY_KEY:
        logger.warning("[SEARCH] No Tavily API key")
        return []

    payload = {
        "api_key":     TAVILY_KEY,
        "query":       query,
        "search_depth": "basic",
        "include_answer": True,
        "max_results": max_results,
        "include_domains": [
            "coindesk.com", "cointelegraph.com", "theblock.co",
            "decrypt.co", "bloomberg.com", "reuters.com",
            "cryptonews.com", "beincrypto.com",
        ],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(TAVILY_BASE, json=payload, timeout=15) as resp:
                resp.raise_for_status()
                data = await resp.json()
                results = data.get("results", [])
                answer  = data.get("answer", "")
                return {
                    "answer":  answer,
                    "results": [
                        {
                            "title":   r.get("title", ""),
                            "url":     r.get("url", ""),
                            "content": r.get("content", "")[:500],
                            "score":   round(r.get("score", 0), 3),
                        }
                        for r in results
                    ],
                }
    except Exception as e:
        logger.error(f"[SEARCH] Tavily error: {e}")
        return {}


# ── Brave Search ─────────────────────────────────────────

async def brave_search(query: str, max_results: int = 5) -> dict:
    """
    Brave Search API — broad web coverage, optional news filter.
    Returns structured results.
    """
    if not BRAVE_KEY:
        logger.warning("[SEARCH] No Brave Search API key")
        return {}

    headers = {
        "Accept":              "application/json",
        "Accept-Encoding":     "gzip",
        "X-Subscription-Token": BRAVE_KEY,
    }
    params = {
        "q":       query,
        "count":   max_results,
        "freshness": "pw",        # past week
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BRAVE_BASE, headers=headers, params=params, timeout=15) as resp:
                resp.raise_for_status()
                data = await resp.json()
                web  = data.get("web", {}).get("results", [])
                return {
                    "results": [
                        {
                            "title":       r.get("title", ""),
                            "url":         r.get("url", ""),
                            "description": r.get("description", "")[:400],
                            "age":         r.get("age", ""),
                        }
                        for r in web
                    ]
                }
    except Exception as e:
        logger.error(f"[SEARCH] Brave error: {e}")
        return {}


# ── Combined search for agents ────────────────────────────

async def search_news(symbol: str, extra_query: str = "") -> dict:
    """
    Perform both Tavily and Brave searches for a trading symbol.
    Returns combined results, deduped, ready for the NewsAnalyst agent.
    """
    base  = symbol.split("/")[0]   # "BTC"
    query = f"{base} crypto news sentiment price analysis {extra_query}".strip()

    tavily_result, brave_result = await asyncio.gather(
        tavily_search(query),
        brave_search(query),
    )

    # Combine and deduplicate by URL
    all_results = []
    seen_urls   = set()

    for r in (tavily_result.get("results", []) if isinstance(tavily_result, dict) else []):
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            all_results.append({"source": "tavily", **r})

    for r in (brave_result.get("results", []) if isinstance(brave_result, dict) else []):
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            all_results.append({"source": "brave", **r})

    return {
        "symbol":       symbol,
        "query":        query,
        "tavily_answer": tavily_result.get("answer", "") if isinstance(tavily_result, dict) else "",
        "articles":     all_results[:8],  # top 8 combined
        "article_count": len(all_results),
    }


if __name__ == "__main__":
    import sys, json
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    result = asyncio.run(search_news(sym))
    print(json.dumps(result, indent=2))
