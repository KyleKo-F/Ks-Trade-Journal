import os
import json
from google import genai
from google.genai import types
from PIL import Image

GEMINI_API_KEY = "AQ.Ab8RN6K7Y0FCoDv1uEAmmsTvrZeIm4hY5dgpb7IJXgePLx8LGQ"

def resize_for_speed(pil_img, max_dim=2400):
    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        new_size = (int(w * scale), int(h * scale))
        return pil_img.resize(new_size, Image.Resampling.LANCZOS)
    return pil_img

def analyze_chart(image_path):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    raw_image = Image.open(image_path)
    image = resize_for_speed(raw_image, max_dim=2400)

    prompt = """
    Analyze this TradingView chart screenshot and extract precise trade details.

    EXACT COLOR-CODED PRICE BADGES ON RIGHT SCALE:
    1. ENTRY PRICE: Solid PURPLE price badge on the right scale (e.g., 1.11901). Read exact badge tag.
    2. TAKE PROFIT (TP): Solid TEAL / CYAN price badge on the right scale at the outer target boundary (e.g., 1.11446). Read ALL digits and decimals with extreme precision—do NOT hallucinate off-scale values.
    3. STOP LOSS (SL): Solid ORANGE / AMBER price badge on the right scale at outer stop boundary (e.g., 1.12016). Read ALL decimals carefully.

    ASSET PAIR FORMATTING:
    - Format forex pairs with a slash (e.g., "EUR/USD" instead of "EURUSD").

    POSITION DIRECTION:
    - If SL (Orange badge) is ABOVE Entry (Purple badge) -> "SELL".
    - If SL (Orange badge) is BELOW Entry (Purple badge) -> "BUY".

    CRITICAL CHRONOLOGICAL STATUS EVALUATION:
    - Trace every candle starting from the entry candle moving right strictly within the target/stop drawing tool.
    - IGNORE background indicator shading (such as red/pink Fair Value Gaps / FVG bands or session boxes). Focus strictly on candlestick wicks vs the position box top/bottom lines.
    - FOR SELL TRADES:
      * Check if ANY candle's lower wick extends DOWN to or past the TEAL TP level. If it touched or pierced TP first without upper wicks piercing the orange SL box top line, status MUST be "TP".
      * If an upper wick pierced the top line of the Orange SL box before reaching TP, status MUST be "SL".
    - FOR BUY TRADES:
      * If upper wick reached TEAL TP level first -> "TP".
      * If lower wick reached ORANGE SL level first -> "SL".
    - Only return "OPEN" if price action remains floating strictly inside the box.

    Return ONLY a valid JSON object:
    {
      "pair": "string (e.g., EUR/USD)",
      "timeframe": "string (e.g., 15m)",
      "direction": "string (BUY or SELL)",
      "entry_price": "string",
      "stop_loss": "string",
      "take_profit": "string",
      "status": "string (TP, SL, or OPEN)"
    }
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[image, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=350
        )
    )

    data = json.loads(response.text)

    entry_str = str(data.get("entry_price", "")).replace(",", "").strip()
    sl_str = str(data.get("stop_loss", "")).replace(",", "").strip()
    tp_str = str(data.get("take_profit", "")).replace(",", "").strip()
    
    pair = str(data.get("pair", "")).strip()
    direction = str(data.get("direction", "BUY")).upper().strip()
    ai_status = str(data.get("status", "OPEN")).upper().strip()

    status = ai_status
    rr_ratio = ""
    pips = ""

    if entry_str and sl_str and tp_str:
        try:
            e = float(entry_str)
            sl = float(sl_str)
            tp = float(tp_str)

            direction = "SELL" if sl > e else "BUY"
            status = ai_status

            risk = abs(e - sl)
            reward = abs(tp - e)

            if risk > 0:
                rr_ratio = f"1:{reward / risk:.2f}"
                
                pair_u = pair.upper()
                if "JPY" in pair_u:
                    mult = 100.0
                elif "XAU" in pair_u or "GOLD" in pair_u:
                    mult = 10.0
                elif "XAG" in pair_u or "SILVER" in pair_u:
                    mult = 100.0
                elif any(coin in pair_u for coin in ["BTC", "ETH", "SOL", "CRYPTO"]):
                    mult = 1.0
                else:
                    mult = 10000.0

                pips = f"{round(reward * mult, 1)}"
        except ValueError:
            pass

    return {
        "pair": pair,
        "timeframe": str(data.get("timeframe", "15m")).strip(),
        "direction": direction,
        "entry_price": entry_str,
        "stop_loss": sl_str,
        "take_profit": tp_str,
        "rr_ratio": rr_ratio,
        "pips": pips,
        "status": status if status in ["OPEN", "TP", "SL"] else "OPEN"
    }

def analyze_trade_performance(image_path, pair, direction, entry, sl, tp, status, trade_type="", language="English"):
    """
    Analyzes a saved trade screenshot and metadata using Gemini Vision 
    to provide a detailed breakdown of execution quality, confluence, and errors.
    """
    if not os.path.exists(image_path):
        return "Error: Screenshot image file not found for this trade."

    client = genai.Client(api_key=GEMINI_API_KEY)
    raw_image = Image.open(image_path)
    image = resize_for_speed(raw_image, max_dim=2400)

    lang_instruction = "Respond entirely in Dutch (Nederlands)." if language == "Dutch" else "Respond in English."

    prompt = f"""
    You are an expert price-action trading mentor. Analyze this executed trade chart screenshot.

    LANGUAGE INSTRUCTION: {lang_instruction}

    TRADE METADATA:
    - Pair: {pair}
    - Setup Type: {trade_type if trade_type else 'N/A'}
    - Direction: {direction}
    - Entry Price: {entry}
    - Stop Loss: {sl}
    - Take Profit: {tp}
    - Outcome Status: {status}

    Provide a concise, highly structured trade breakdown:

    1. WHAT WENT RIGHT / WELL:
       - Point out technical confluence (e.g., Fair Value Gaps, liquidity sweeps, market structure shifts, session highs/lows).
       - Note proper risk/reward or entry execution.

    2. WHAT WENT WRONG / RISKS:
       - Explain key failure factors if SL was hit or trade struggled (e.g., entering into high-timeframe resistance, tight stop placement, counter-trend trading).

    3. KEY TAKEAWAYS & LESSONS:
       - Give 2 actionable recommendations for similar future setups.

    Keep your tone professional, direct, and constructive. Use bullet points and clear formatting.
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=600
            )
        )
        return response.text
    except Exception as err:
        return f"Failed to generate analysis: {str(err)}"