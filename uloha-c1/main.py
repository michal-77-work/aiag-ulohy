import os
import json
import requests
from openai import OpenAI
from pprint import pprint
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

# WMO weather codes -> human readable description
# https://open-meteo.com/en/docs#weathervariables
WEATHER_CODES = {
    0: "jasno",
    1: "prevažne jasno",
    2: "polooblačno",
    3: "zamračené",
    45: "hmla",
    48: "namŕzajúca hmla",
    51: "slabé mrholenie",
    53: "mrholenie",
    55: "silné mrholenie",
    61: "slabý dážď",
    63: "dážď",
    65: "silný dážď",
    71: "slabé sneženie",
    73: "sneženie",
    75: "silné sneženie",
    80: "prehánky",
    95: "búrka",
    99: "silná búrka s krupobitím",
}


# Function Implementation
def get_weather(city: str):
    """Fetch the current weather for a city using the free Open-Meteo API (no API key required)."""

    # 1. Geocode the city name to latitude/longitude
    geo_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "en", "format": "json"},
    )
    geo_response.raise_for_status()
    geo_results = geo_response.json().get("results")

    if not geo_results:
        return {"error": f"City '{city}' not found."}

    location = geo_results[0]
    latitude = location["latitude"]
    longitude = location["longitude"]

    # 2. Fetch the current weather for the coordinates
    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": True,
        },
    )
    weather_response.raise_for_status()
    current_weather = weather_response.json()["current_weather"]

    return {
        "city": location.get("name", city),
        "country": location.get("country"),
        "temperature_celsius": current_weather["temperature"],
        "windspeed_kmh": current_weather["windspeed"],
        "condition": WEATHER_CODES.get(current_weather["weathercode"], "neznáme počasie"),
    }


# Define custom tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Use this function to get the current weather for a given city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The city name, e.g. Bratislava",
                    }
                },
                "required": ["city"],
            },
        },
    },
]

available_functions = {
    "get_weather": get_weather,
}


# Function to process messages and handle function calls
def get_completion_from_messages(messages, model="gpt-5.4-nano"):
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,  # Custom tools
        tool_choice="auto",  # Allow AI to decide if a tool should be called
    )

    response_message = response.choices[0].message

    print("First response:", response_message)

    if response_message.tool_calls:
        # The assistant message with the tool call(s) must be added to the history
        messages.append(response_message)

        # A model can request multiple tool calls at once - handle all of them
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            # Call the function
            function_to_call = available_functions[function_name]
            function_response = function_to_call(**function_args)

            print(f"Tool '{function_name}' called with {function_args} -> {function_response}")

            # Return the function's result back to the LLM
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(function_response),
                }
            )

        # Second call to get the final response based on the tool output(s)
        second_response = client.chat.completions.create(
            model=model, messages=messages, tools=tools, tool_choice="auto"
        )
        final_answer = second_response.choices[0].message

        print("Second response:", final_answer)
        return final_answer

    return response_message


# Example usage
messages = [
    {"role": "system", "content": "You are a helpful AI assistant."},
    {"role": "user", "content": "Aké je aktuálne počasie v Bratislave?"},
]

response = get_completion_from_messages(messages)
print("--- Full response: ---")
pprint(response)
print("--- Response text: ---")
print(response.content)
