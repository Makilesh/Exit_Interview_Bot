"""
Question bank and follow-up variants for the exit interview.
"""

QUESTION_BANK: list[str] = [
    "What is the primary reason for leaving the organization?",
    "How would you describe your overall experience with the company?",
    "What did you like most about working here?",
    "What could the company improve?",
    "How was your relationship with your manager and team?",
    "Would you recommend this company to others? Why or why not?",
]

FOLLOWUP_VARIANTS: dict[int, list[str]] = {
    0: [
        "Could you tell me more about what led to that decision?",
        "Was there a specific event or moment that influenced your choice?",
        "How long had you been considering leaving before making this decision?",
    ],
    1: [
        "Can you share a specific example that shaped your experience?",
        "Were there particular phases in your tenure that stood out, positively or negatively?",
        "How did your experience change over time?",
    ],
    2: [
        "Could you elaborate on what made that aspect particularly positive?",
        "Is there something specific about that experience that other companies should replicate?",
        "How important was that factor in your day-to-day satisfaction?",
    ],
    3: [
        "Can you give a specific example of where things could have been better?",
        "If you could change one thing about the company, what would it be?",
        "Were there processes or policies that particularly frustrated you?",
    ],
    4: [
        "Could you share a specific experience with your manager that stands out?",
        "How did team dynamics affect your daily work?",
        "Was there anything about the management style that you found challenging?",
    ],
    5: [
        "What would be the main reason behind your recommendation or lack thereof?",
        "What kind of person do you think would thrive in this company?",
        "Is there anything specific that would change your recommendation?",
    ],
}
