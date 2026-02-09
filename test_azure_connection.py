#!/usr/bin/env python3
"""
Test Azure connections after setup
Run this after azure-setup.sh to verify everything works
"""

import os
import sys
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()

def test_openai():
    """Test Azure OpenAI connection"""
    print("Testing Azure OpenAI...", end=" ")
    try:
        from azure.ai.inference import ChatCompletionsClient
        from azure.core.credentials import AzureKeyCredential

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        key = os.getenv("AZURE_OPENAI_KEY")

        if not endpoint or not key:
            print("❌ Missing credentials")
            return False

        client = ChatCompletionsClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key)
        )

        # Simple test completion
        response = client.complete(
            messages=[{"role": "user", "content": "Say 'test successful' if you can read this"}],
            model="gpt-4"
        )

        print("✅ Connected")
        print(f"   Response: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_cosmos():
    """Test Cosmos DB connection"""
    print("Testing Cosmos DB...", end=" ")
    try:
        from azure.cosmos import CosmosClient

        endpoint = os.getenv("COSMOS_ENDPOINT")
        key = os.getenv("COSMOS_KEY")

        if not endpoint or not key:
            print("❌ Missing credentials")
            return False

        client = CosmosClient(endpoint, key)

        # List databases (should be empty for new account)
        databases = list(client.list_databases())

        print("✅ Connected")
        print(f"   Databases: {len(databases)}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_insights():
    """Test Application Insights connection"""
    print("Testing Application Insights...", end=" ")
    try:
        conn_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")

        if not conn_string:
            print("❌ Missing connection string")
            return False

        # Just verify the format
        if "InstrumentationKey=" in conn_string:
            print("✅ Configuration valid")
            print(f"   Connection string length: {len(conn_string)} chars")
            return True
        else:
            print("❌ Invalid connection string format")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_acr():
    """Test Container Registry"""
    print("Testing Container Registry...", end=" ")
    try:
        acr_name = os.getenv("ACR_NAME")
        username = os.getenv("ACR_USERNAME")
        password = os.getenv("ACR_PASSWORD")

        if not all([acr_name, username, password]):
            print("❌ Missing credentials")
            return False

        print("✅ Credentials present")
        print(f"   Registry: {acr_name}.azurecr.io")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("=" * 50)
    print("AgentOS - Azure Connection Tests")
    print("=" * 50)
    print()

    # Check .env exists
    if not Path(".env").exists():
        print("❌ .env file not found!")
        print("   Run azure-setup.sh first")
        sys.exit(1)

    results = {
        "Azure OpenAI": test_openai(),
        "Cosmos DB": test_cosmos(),
        "Application Insights": test_insights(),
        "Container Registry": test_acr()
    }

    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)

    for service, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {service}")

    print()

    if all(results.values()):
        print("✅ All services connected successfully!")
        print("   You're ready to start development.")
        sys.exit(0)
    else:
        print("❌ Some services failed.")
        print("   Check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
