#!/usr/bin/env python3
"""
Agentic Debugger for AI Trading System Pipelines
Usage: python debug_crew.py
"""

import os
import subprocess
import sys
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai.llm import LLM
from litellm import completion

# Load cloud credentials (you will edit .env.cloud)
load_dotenv("/workspaces/ai-trading-system/.env.cloud")

# Use LiteLLM proxy (we'll start it automatically)
# For now, we use direct Groq free tier (if you have keys) or fallback to a local mock.
# Since you may not have keys yet, we will use a simple local LLM emulator for debugging.
# But the real power comes with Groq. I'll include instructions.

class Debugger:
    def __init__(self):
        # Try to use Groq if API key is provided, else fallback to a basic function
        self.groq_key = os.getenv("GROQ_API_KEY")
        if self.groq_key and self.groq_key != "placeholder":
            self.llm = LLM(model="groq/llama-3.1-8b-instant", api_key=self.groq_key)
        else:
            # Fallback: simple echo (will not fix but will simulate)
            self.llm = None
            print("Warning: No GROQ_API_KEY set. Using basic logger. To get free key: https://console.groq.com")

    def run_command(self, cmd, cwd=None):
        """Run a shell command and return stdout, stderr, returncode"""
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        return result.stdout, result.stderr, result.returncode

    def debug_data_pipeline(self):
        """Run data pipeline and capture errors, then attempt to fix."""
        print("\n=== DEBUGGING DATA PIPELINE ===")
        # First, try to run the pipeline with a small sample.
        # We will create a test sample.
        sample_csv = "data_pipeline/sample.csv"
        if not os.path.exists(sample_csv):
            # Create a minimal sample from your existing data? For now, we will skip.
            # Instead we just run the pipeline and see what fails.
            pass

        stdout, stderr, rc = self.run_command("cd data_pipeline && python run_pipeline.py")
        if rc == 0:
            print("✅ Data pipeline ran successfully.")
            return True
        else:
            print("❌ Data pipeline failed. Errors:")
            print(stderr[-2000:])  # last 2000 chars
            # Now ask an LLM (if available) to suggest fixes
            if self.llm:
                fix_prompt = f"""
                The data pipeline failed with this error:
                {stderr[-1500]}

                The code is in data_pipeline/ directory.
                Suggest specific code changes to fix the problem.
                Focus on: database connection, file paths, column names, or missing tables.
                Return ONLY the exact Python code changes or environment variable settings.
                """
                response = completion(model="groq/llama-3.1-8b-instant", messages=[{"role": "user", "content": fix_prompt}])
                suggestion = response.choices[0].message.content
                print("LLM Suggestion:\n", suggestion)
                # Write suggestion to a file for manual review
                with open("debug_suggestions.txt", "a") as f:
                    f.write("DATA PIPELINE:\n" + suggestion + "\n\n")
            else:
                print("No LLM key – please manually fix based on error above.")
            return False

    def debug_research_pipeline(self):
        """Run research pipeline and capture errors."""
        print("\n=== DEBUGGING RESEARCH PIPELINE ===")
        stdout, stderr, rc = self.run_command("cd quant_research_org && python main.py")
        if rc == 0:
            print("✅ Research pipeline ran successfully.")
            return True
        else:
            print("❌ Research pipeline failed. Errors:")
            print(stderr[-2000:])
            if self.llm:
                fix_prompt = f"""
                The research pipeline failed with:
                {stderr[-1500]}

                Suggest fixes for quant_research_org/ code.
                Focus on imports, Redis connection, or feature generation logic.
                """
                response = completion(model="groq/llama-3.1-8b-instant", messages=[{"role": "user", "content": fix_prompt}])
                suggestion = response.choices[0].message.content
                print("LLM Suggestion:\n", suggestion)
                with open("debug_suggestions.txt", "a") as f:
                    f.write("RESEARCH PIPELINE:\n" + suggestion + "\n\n")
            else:
                print("No LLM key – manually fix.")
            return False

    def run_all(self):
        print("Starting Agentic Debugger for AI Trading System")
        data_ok = self.debug_data_pipeline()
        research_ok = self.debug_research_pipeline()
        if data_ok and research_ok:
            print("\n🎉 All pipelines are working! Now you can integrate with your local system.")
        else:
            print("\n⚠️ Some pipelines still have issues. Check debug_suggestions.txt for recommended fixes.")

if __name__ == "__main__":
    debugger = Debugger()
    debugger.run_all()