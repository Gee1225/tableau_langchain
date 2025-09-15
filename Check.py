import sys
import os
import warnings # Import warnings module

print(f"Python Version: {sys.version}")
print(f"Current Working Directory: {os.getcwd()}")
print("-" * 20)

try:
    import langchain
    print(f"✅ langchain version: {langchain.__version__}")
    import langchain_openai
    print("✅ langchain_openai imported")
    import langgraph
    print(f"✅ langgraph imported")
    import langchain_community
    print("✅ langchain_community imported")
    import langchain_tableau # Check if our custom package is importable
    print("✅ langchain_tableau imported")
    import slack_sdk
    print(f"✅ slack_sdk imported")
    from dotenv import find_dotenv, load_dotenv
    print("✅ dotenv imported")
    print("-" * 20)
    print("Core libraries imported successfully!")
    print("-" * 20)

    # Check for .env file in the current directory OR parent directories
    env_path = find_dotenv() # Find the path first

    if env_path:
         print(f"✅ .env file found and loaded from: {env_path}")
         # Optionally check for a specific key existence - useful for debugging later
         # Example: Check if a key expected from the .env URL exists
         # You can uncomment and adapt this check once you know a key name from the provided .env content
         # expected_key = "OPENAI_API_KEY" # Replace with an actual key name
         # if os.getenv(expected_key):
         #    print(f"   - Found {expected_key} in environment.")
         # else:
         #    print(f"   - WARNING: {expected_key} not found (is it in your .env file?).")
    else:
         print("🟡 Warning: .env file not found in current or parent directories.")
         print("   Please ensure you have completed Step 4 correctly:")
         print("   1. Create the file named exactly '.env' (dot included) at the ROOT of the 'tableau_langchain' project.")
         print("   2. Paste the entire content provided via the URL into this file.")
         print("   3. Save the file.")
         print(f"   (Searching started from: {os.getcwd()})")


    # Reset warnings filter after use if desired
    # warnings.resetwarnings()

except ImportError as e:
    print("-" * 20)
    if 'langchain_tableau' in str(e):
        print(f"❌ ERROR: Failed to import 'langchain_tableau' - {e}.")
        print("   Did you run 'pip install -e .' INSIDE the 'tableau_langchain' directory (Step 3)?")
        print(f"   Current directory is: {os.getcwd()}")
    else:
        print(f"❌ ERROR: Failed to import library - {e}.")
        print("   Please double-check the installation steps (pip install commands in Step 1 and Step 3).")
        print("   Ensure your virtual environment is activated if you are using one.")
except Exception as e:
    print("-" * 20)
    print(f"❌ An unexpected error occurred: {e}")

print("-" * 20)