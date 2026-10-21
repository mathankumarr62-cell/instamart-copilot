"""Zero-shot and few-shot CLASSIFY system prompts (task 3)."""

ZERO_SHOT = ('CLASSIFY the support ticket into one category: billing, delivery, technical or fraud. '
             'Reply with JSON only: {"category": "...", "reason": "..."}')

FEW_SHOT = (ZERO_SHOT + "\n"
            "EXAMPLES:\n"
            'Ticket: Someone used my card for an order I never placed. -> {"category": "fraud", "reason": "unauthorized use"}\n'
            'Ticket: I was charged twice for one order. -> {"category": "billing", "reason": "double charge"}\n'
            'Ticket: The app shows an error at checkout. -> {"category": "technical", "reason": "app error"}\n'
            'Ticket: My groceries arrived two hours late. -> {"category": "delivery", "reason": "late order"}')
