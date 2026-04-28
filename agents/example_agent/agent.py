import datetime
import os
import asyncio
from zoneinfo import ZoneInfo
from google.adk.agents import Agent


def get_current_time(city: str) -> dict:
    """Returns the current time in a supported city."""
    tz_map = {
        "vienna": "Europe/Vienna",
        "new york": "America/New_York",
        "london": "Europe/London",
        "san francisco": "America/Los_Angeles",
    }
    tz = tz_map.get(city.lower())
    if not tz:
        return {
            "status": "error",
            "error_message": f"Unknown city '{city}'. Try one of: {', '.join(sorted(tz_map))}",
        }

    now = datetime.datetime.now(ZoneInfo(tz))
    return {
        "status": "success",
        "report": f"The current time in {city} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}",
    }


# Your actual agent (LLM + tools)
agent = Agent(
    name="time_agent",
    model=os.getenv("ADK_MODEL", "gemini-2.5-flash"),
    description="Answers questions about the current time in supported cities.",
    instruction="Be helpful. When asked about time in a city, call get_current_time.",
    tools=[get_current_time],
)