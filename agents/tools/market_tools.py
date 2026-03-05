"""
market_tools.py — LangChain-compatible tools for market data
Agents use these to fetch live prices, indicators, orderbook, and news.
"""

import os
import json
import aiohttp
from langchain_core.tools import tool
from loguru import logger


@tool
async def get_indicators(symbol: str, timeframe: str = "1h") -> str:
    """
    Get technical indicators for a trading symbol.
    Returns RSI, Bollinger Bands, MACD, ATR, and VWAP values.

    Args:
        symbol: Trading pair e.g. 'BTC/USDT'
        timeframe: Candle timeframe e.g. '1h', '4h', '1d'
    """
    from data.indicators import get_indicators as _get_indicators
    result = await _get_indicators(symbol, timeframe)
    return json.dumps(result, default=str)


@tool
async def get_current_price(symbol: str) -> str:
    """
    Get the current live price for a trading symbol from Bybit.

    Args:
        symbol: Trading pair e.g. 'BTC/USDT' or 'BTCUSDT'
    """
    bybit_symbol = symbol.replace("/", "")
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={bybit_symbol}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                data = await resp.json()
                ticker = data["result"]["list"][0]
                return json.dumps({
                    "symbol":    symbol,
                    "price":     float(ticker["lastPrice"]),
                    "bid":       float(ticker["bid1Price"]),
                    "ask":       float(ticker["ask1Price"]),
                    "volume_24h": float(ticker["volume24h"]),
                    "change_24h": float(ticker["price24hPcnt"]) * 100,
                })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
async def get_orderbook(symbol: str, depth: int = 10) -> str:
    """
    Get the current order book for a symbol — shows buy/sell walls.

    Args:
        symbol: Trading pair e.g. 'BTC/USDT'
        depth: Number of levels to fetch (5, 10, 25, 50)
    """
    bybit_symbol = symbol.replace("/", "")
    url = f"https://api.bybit.com/v5/market/orderbook?category=linear&symbol={bybit_symbol}&limit={depth}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                data = await resp.json()
                book = data["result"]
                bids = [[float(p), float(q)] for p, q in book["b"][:5]]
                asks = [[float(p), float(q)] for p, q in book["a"][:5]]
                spread = asks[0][0] - bids[0][0] if bids and asks else None
                return json.dumps({
                    "symbol":  symbol,
                    "top_bids": bids,   # [price, qty]
                    "top_asks": asks,
                    "spread":  round(spread, 2) if spread else None,
                    "bid_wall": max(bids, key=lambda x: x[1]) if bids else None,
                    "ask_wall": max(asks, key=lambda x: x[1]) if asks else None,
                })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
async def search_news(query: str, max_results: int = 5) -> str:
    """
    Search for recent crypto news and market sentiment.

    Args:
        query: Search query e.g. 'Bitcoin price prediction'
        max_results: Number of results to return (1-10)
    """
    from data.search import search_news as _search_news
    try:
        results = await _search_news(query, max_results=max_results)
        return json.dumps(results[:max_results], default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
async def run_backtest(strategy_json: str) -> str:
    """
    Run a backtest on a trading strategy using historical data.
    Returns winrate, Sharpe ratio, max drawdown and assessment.

    Args:
        strategy_json: JSON string with strategy definition:
            {
                "name": "RSI Oversold Reversal",
                "direction": "long",
                "entry_conditions": [
                    {"indicator": "rsi_14", "op": "<", "value": 30},
                    {"indicator": "bb_pct_b", "op": "<", "value": 0.1}
                ],
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.05
            }
    """
    from backtest.auto_backtest import run_backtest as _run_backtest
    try:
        strategy = json.loads(strategy_json)
        result = await _run_backtest(strategy)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
async def check_absorption(symbol: str) -> str:
    """
    Check for market absorption or exhaustion at key structural levels (POC, VAH, VAL).
    Used to detect potential reversals when high volume fails to move price.

    Args:
        symbol: Trading pair e.g. 'BTC/USDT'
    """
    from data.absorption import detect_absorption
    try:
        result = await detect_absorption(symbol)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
async def execute_python(code: str, symbol: str = "BTC/USDT") -> str:
    """
    Execute Python code to analyse market data. Candle data is available as `df` (pandas DataFrame).
    Only pandas, numpy, and math libraries are available.

    Args:
        code: Python code to execute. Use `print()` to return results.
        symbol: Symbol to load candle data for
    """
    from data.code_executor import execute_with_candles
    result = await execute_with_candles(code, symbol)
    return json.dumps(result.to_dict())
