from typing import Any


# Temporary mock implementation.
# Replace the hardcoded response with a BigQuery query during integration.
def get_major_data(major_name: str) -> dict[str, Any]:
    """
    Retrieve AI exposure and career information for one college major.

    Args:
        major_name: Name of the college major, such as Computer Science.

    Returns:
        Structured exposure, pay, growth, and occupation data.
    """
    print(f"TOOL CALLED for: {major_name}")

    return {
        "status": "success",
        "source": "mock",
        "major_name": major_name,
        "exposure": 9.0,
        "median_pay": 99000,
        "growth": "faster",
        "occupations": [
            {
                "soc": "15-1252",
                "title": "Software developers",
                "exposure": 9.0,
            }
        ],
    }