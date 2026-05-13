# 🤖 AI-Powered Data Dashboard with Agentic Workflow

An interactive data visualization dashboard built with Streamlit, LangGraph, and ChatGroq. This project utilizes a multi-agent architecture to autonomously suggest, generate, and validate Plotly code based on user-uploaded datasets.

## 🏗️ Architecture & Agentic Flow

The system separates the reasoning tasks from the coding tasks, utilizing a Human-In-The-Loop (HITL) step and a self-correcting ReAct (Reason + Act) validation loop to ensure reliable code generation.

```mermaid
graph TD
    %% Styling
    classDef user fill:#4A90E2,stroke:#333,stroke-width:2px,color:#fff;
    classDef agent fill:#50E3C2,stroke:#333,stroke-width:2px,color:#000;
    classDef llm fill:#F5A623,stroke:#333,stroke-width:2px,color:#000;
    classDef system fill:#9B9B9B,stroke:#333,stroke-width:2px,color:#fff;

    A[User Uploads CSV]:::user --> B[Extract Metadata: df.info + df.head]:::system
    B --> C[Planner Agent]:::agent
    
    C -- Context --> D((ChatGroq LLM)):::llm
    D -- 3-5 Plot Ideas --> E{Human-In-The-Loop}:::user
    
    E -- Selects Desired Plots --> F[Start ReAct Workflow]:::system

    subgraph LangGraph ReAct Loop [Self-Correcting Code Generation]
        direction TB
        F --> G[Coding Agent]:::agent
        G -- Prompt: Write Plotly Code --> H((ChatGroq LLM)):::llm
        H -- Python Code --> I[Code Cleaning & Regex]:::system
        I --> J[Validator Node]:::agent
        J -- exec in local scope --> K{Execution Status}
        
        K -- Exception Raised (iters < 3) --> L[Extract Python Traceback]:::system
        L -- Inject Error into Prompt --> G
    end

    K -- Success --> M[Final Sanitized Code]:::system
    M --> N[Streamlit App Renders Plots]:::system