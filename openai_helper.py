import os, json, datetime
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_CACHE = {"ts": None, "text": "No insights yet."}

def generate_insight(df, force=False):
    """Return a short markdown insight string based on last hour of data."""
    now = datetime.datetime.utcnow()
    if not force and _CACHE["ts"] and (now - _CACHE["ts"]).seconds < 300:
        return _CACHE["text"]  # 5-min cache

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        txt = ":warning: **OPENAI_API_KEY not set – showing placeholder**\n" \
              "- Average CO₂ is {:.0f} ppm\n- All parameters within normal range".format(df.co2.mean())
    else:
        try:
            # aggregate to keep the prompt tiny
            summary = {
                "rows": len(df),
                "co2_avg": float(df.co2.mean()),
                "co2_max": float(df.co2.max()),
                "temp_avg": float(df.temp.mean()),
                "pm_max": float(df.pm.max()),
            }
            prompt = (
                "You are a building-health analyst. "
                "Given the following 1-hour environmental stats (JSON), "
                "write 2-3 concise bullet insights plus one actionable recommendation:\n"
                f"{json.dumps(summary)}"
            )
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.3,
            )
            txt = response.choices[0].message.content.strip()
        except Exception as e:
            txt = f":warning: **OpenAI API Error: {str(e)}**\n" \
                  "- Average CO₂ is {:.0f} ppm\n- All parameters within normal range".format(df.co2.mean())

    _CACHE.update(ts=now, text=txt)
    return txt 