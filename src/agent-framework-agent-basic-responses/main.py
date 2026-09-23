# Copyright (c) Microsoft. All rights reserved.

import os
from dotenv import load_dotenv
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

# Load environment variables from .env file
load_dotenv()


def main():
    document_client = DocumentAnalysisClient(
        endpoint=os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"],
        credential=AzureKeyCredential(
            os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
        ),
    )
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_NAME")
    if not model_name:
        raise RuntimeError(
            "Model deployment name is not configured. Set "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME or FOUNDRY_MODEL_NAME."
        )

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model_name,
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions="""You are a Resume Analysis Agent.

Analyze the candidate's resume using only evidence found in the provided resume text.

Evaluate:
1. Structure /10
2. Skills /15
3. Experience /20
4. Projects /15
5. Achievements /10
6. Education /10
7. Job Alignment /15
8. Clarity & Language /5

Return:
- Overall score /100
- Category scores with brief reasons
- 3 strengths
- 5 improvements
- Missing information
- Weak resume bullets and improved versions
- Job matches and gaps if a job description is provided

Rules:
- Never invent skills, experience, employers, achievements, qualifications, or metrics.
- If information is absent, say "Not found".
- Clearly separate facts from recommendations.
- Keep the response concise.
- Return structured JSON.""",
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
