import os
from langchain_openai import ChatOpenAI 

client = os.getenv("OPENAI_API_KEY")

def generate_sql(user_input: str):
    prompt = f"""
    You are an expert SQL Server developer.

    Convert the following user request into a SQL query.
    Only return SQL, no explanation.

    User request:
    {user_input}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip()