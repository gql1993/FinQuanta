"""Shared UI tokens for desktop panels."""

# Four-level application font scale requested by product/UI:
# l1=11, l2=12, l3=13, l4=14
FONT_TOKENS = {
    "l1": 11,
    "l2": 12,
    "l3": 13,
    "l4": 14,
}

# Semantic aliases for readability in panel code.
APP_FONT = {
    "caption": FONT_TOKENS["l1"],
    "body": FONT_TOKENS["l2"],
    "emphasis": FONT_TOKENS["l3"],
    "section": FONT_TOKENS["l4"],
    "page_title": FONT_TOKENS["l4"],
    "hero_title": FONT_TOKENS["l4"],
}
