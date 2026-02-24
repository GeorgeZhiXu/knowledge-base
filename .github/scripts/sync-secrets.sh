#!/bin/bash
# Central secret sync script for multiple repositories
# Store this on your Mac Mini and run via cron or manually

# Define your repositories
REPOS=(
  "GeorgeZhiXu/knowledge-base"
  "GeorgeZhiXu/AiChatBot"
  "GeorgeZhiXu/TingXieJs"
  # Add more repos as needed
)

# Load secrets from a central .env file
source /Users/xuzhi/.github-secrets.env

# Sync secrets to all repos
for repo in "${REPOS[@]}"; do
  echo "Updating secrets for $repo..."

  # AWS Bedrock Token
  if [ -n "$AWS_BEARER_TOKEN_BEDROCK" ]; then
    gh secret set AWS_BEARER_TOKEN_BEDROCK \
      --repo "$repo" \
      --body "$AWS_BEARER_TOKEN_BEDROCK"
  fi

  # Add more secrets as needed
  if [ -n "$DEEPSEEK_API_KEY" ]; then
    gh secret set DEEPSEEK_API_KEY \
      --repo "$repo" \
      --body "$DEEPSEEK_API_KEY"
  fi

  # Mac Mini deployment secrets
  gh secret set MAC_MINI_HOST --repo "$repo" --body "$MAC_MINI_HOST"
  gh secret set MAC_MINI_USER --repo "$repo" --body "$MAC_MINI_USER"
  gh secret set MAC_MINI_SSH_KEY --repo "$repo" --body "$MAC_MINI_SSH_KEY"
done

echo "Secret sync complete!"