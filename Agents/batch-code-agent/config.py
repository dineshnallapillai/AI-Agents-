"""Configuration for the batch code agent."""

# Backend: "anthropic" (direct API + batch) or "bedrock" (AWS Bedrock)
BACKEND = "bedrock"

# AWS Bedrock settings
AWS_REGION = "eu-west-1"
# Set to None to use default credential chain (env vars, ~/.aws/credentials, IAM role)
AWS_PROFILE = None

# Model selection
# For Bedrock, use the Bedrock model IDs:
BEDROCK_MODELS = {
    "sonnet": "anthropic.claude-sonnet-4-20250514-v1:0",
    "haiku": "anthropic.claude-haiku-4-5-20251001-v1:0",
    "opus": "anthropic.claude-opus-4-7-20250415-v1:0",
}

# For direct Anthropic API:
ANTHROPIC_MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
    "opus": "claude-opus-4-7-20250415",
}

# Which model to use (shortname)
MODEL_CHOICE = "sonnet"

# Max output tokens per response
MAX_TOKENS = 8096

# Seconds between batch status polls (only for Anthropic batch mode)
POLL_INTERVAL = 5

# Max agentic loop turns before stopping
MAX_TURNS = 50

# Pricing per 1M tokens
# Bedrock on-demand pricing (same as Anthropic real-time):
PRICING = {
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
    },
    "haiku": {
        "input": 0.80,
        "output": 4.0,
    },
    "opus": {
        "input": 15.0,
        "output": 75.0,
    },
}

# Batch discount (only applies to direct Anthropic API batches)
BATCH_DISCOUNT = 0.5
