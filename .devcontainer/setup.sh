#!/bin/bash
set -e

echo "========================================="
echo " Installing CrewAI + LiteLLM + Dependencies"
echo "========================================="

# Upgrade pip
pip install --upgrade pip

# Install data pipeline dependencies (if requirements.txt exists, else basic)
if [ -f "data_pipeline/requirements.txt" ]; then
    pip install -r data_pipeline/requirements.txt
else
    pip install pandas sqlalchemy psycopg2-binary pyarrow pydantic
fi

# Install research pipeline dependencies (if any)
if [ -f "quant_research_org/requirements.txt" ]; then
    pip install -r quant_research_org/requirements.txt
fi

# Install agentic tools
pip install litellm[proxy] crewai langchain-groq langchain-google-genai redis python-dotenv tenacity

# Create a .env template
cat > /workspaces/ai-trading-system/.env.cloud << 'EOF'
# Neon PostgreSQL
DATABASE_URL=postgresql://...
# Redis Cloud
REDIS_HOST=your_redis_host:port
REDIS_PASSWORD=your_password
# LLM API Keys (get free later if you want)
GROQ_API_KEY=placeholder
GEMINI_API_KEY=placeholder
EOF

echo "Setup complete. Edit /workspaces/ai-trading-system/.env.cloud with your real credentials."