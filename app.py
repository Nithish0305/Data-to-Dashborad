import streamlit as st
import pandas as pd
import io
from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import plotly.express as px
import re

def clean_code(code_str):
    """Removes Markdown backticks and stray show() commands from LLM output."""
    # Remove markdown wrappers
    code = re.sub(r"^```(?:python)?\s*", "", code_str, flags=re.MULTILINE)
    code = re.sub(r"```\s*$", "", code, flags=re.MULTILINE)
    # NEW: Remove any instance of fig.show()
    code = re.sub(r"^\s*fig\.show\(\)\s*$", "", code, flags=re.MULTILINE)
    
    return code.strip()

# --- 1. CONFIGURATION & STATE ---
st.set_page_config(page_title="AI Data Dashboard", layout="wide")

class AgentState(TypedDict):
    df_context: str
    suggestions: List[str]
    selected_plots: List[str]
    generated_code: List[str]
    csv_data: pd.DataFrame
    errors: str           # NEW: Store execution errors
    iterations: int       # NEW: Prevent infinite loops

# Initialize Groq LLM
llm = ChatGroq(temperature=0, model_name="llama-3.3-70b-versatile", groq_api_key="YOUR_GROQ_API_KEY")

# --- 2. AGENT NODES ---

def planner_agent(state: AgentState):
    """Suggests 3-5 interesting plots based on data head."""
    prompt = f"""
    You are a data analyst. Based on the following data summary, suggest 3 specific Plotly Express charts.
    Format your response as a simple bulleted list of plot descriptions.
    
    Data Summary:
    {state['df_context']}
    """
    response = llm.invoke([SystemMessage(content=prompt)])
    suggestions = [s.strip("- ") for s in response.content.strip().split("\n") if s.strip()]
    return {"suggestions": suggestions[:3]}

def coding_agent(state: AgentState):
    selected = state['selected_plots']
    error_msg = state.get('errors', '')
    
    prompt = f"""
    You are a Python Expert. Generate Plotly Express code for: {selected}.
    The dataframe is loaded as `df`. Create a figure named 'fig'.
    Separate multiple plots with '---'. No explanations.
    IMPORTANT: DO NOT include `fig.show()` or any rendering commands. Just assign the plot to the `fig` variable.
    """
    
    # If the agent previously failed, inject the error for correction
    if error_msg:
         prompt += f"\n\nPREVIOUS ERROR TO FIX:\n{error_msg}\nCorrect your code based on this error."

    response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=f"Data columns: {state['df_context']}")])
    code_blocks = response.content.split("---")
    
    # Increment iteration count
    current_iters = state.get('iterations', 0)
    return {"generated_code": code_blocks, "iterations": current_iters + 1, "errors": ""}

def code_validator(state: AgentState):
    """Executes the code securely to check for errors."""
    df = state['csv_data']
    codes = state['generated_code']
    error_log = ""
    
    for code in codes:
        cleaned = clean_code(code)
        try:
            local_scope = {"df": df, "px": px}
            exec(cleaned, {}, local_scope) # Test execution
        except Exception as e:
            error_log += f"Code:\n{cleaned}\nError: {str(e)}\n\n"
            
    return {"errors": error_log}


def should_continue(state: AgentState):
    """Determines if we need to route back to the coder."""
    if state.get("errors") and state.get("iterations", 0) < 3:
        return "coder" # Loop back and fix
    return END # Finish

# --- 3. GRAPH CONSTRUCTION ---

# We create a specific graph just for the ReAct coding loop
react_workflow = StateGraph(AgentState)
react_workflow.add_node("coder", coding_agent)
react_workflow.add_node("validator", code_validator)

react_workflow.set_entry_point("coder")
react_workflow.add_edge("coder", "validator")

# Conditional logic: If validator finds errors, go back to coder. Else, END.
react_workflow.add_conditional_edges("validator", should_continue)

react_graph = react_workflow.compile()

# --- 4. STREAMLIT UI ---

st.title("🤖 AI-Powered Data Dashboard")

uploaded_file = st.file_uploader("Upload your CSV", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.write("### Data Preview", df.head())
    
    # Prepare context
    buffer = io.StringIO()
    df.info(buf=buffer)
    df_context = f"Columns and Types:\n{buffer.getvalue()}\n\nSample Data:\n{df.head(3).to_string()}"

    # Initialize State
    if "agent_state" not in st.session_state:
        st.session_state.agent_state = {
            "df_context": df_context,
            "suggestions": [],
            "selected_plots": [],
            "generated_code": [],
            "csv_data": df,
            "errors": "",
            "iterations": 0
        }

    # Step 1: Get Suggestions (Calling the function directly is fine here since it's one step)
    if st.button("Analyze Data"):
        result = planner_agent(st.session_state.agent_state)
        st.session_state.agent_state["suggestions"] = result["suggestions"]

    # Step 2: HITL - User Selection
    if st.session_state.agent_state["suggestions"]:
        st.write("### AI Suggestions")
        selected = st.multiselect("Select the plots you want to generate:", 
                                  st.session_state.agent_state["suggestions"])
        
        if st.button("Generate Selected Plots") and selected:
            st.session_state.agent_state["selected_plots"] = selected
            st.session_state.agent_state["iterations"] = 0 # Reset iterations
            
            with st.spinner("Generating and Validating code..."):
                # RUN THE LANGGRAPH LOOP instead of the raw function!
                final_state = react_graph.invoke(st.session_state.agent_state)
                
                # Update our session state with the final successful code
                st.session_state.agent_state["generated_code"] = final_state["generated_code"]
                
                if final_state["errors"]:
                    st.warning("The agent tried to fix the code but failed after 3 attempts. See below.")

    # Step 3: Execution & Rendering
    if st.session_state.agent_state["generated_code"]:
        st.write("### Dashboard")
        
        for idx, code in enumerate(st.session_state.agent_state["generated_code"]):
            cleaned_code = clean_code(code) 
            
            try:
                local_scope = {"df": df, "px": px}
                exec(cleaned_code, {}, local_scope)
                
                if "fig" in local_scope:
                    # Your fix for the deprecation warning is perfectly implemented here
                    st.plotly_chart(local_scope["fig"], width="stretch", key=f"plot_{idx}")
                    
            except Exception as e:
                st.error(f"Error rendering plot {idx+1}: {e}")
                with st.expander("View generated code"):
                    st.code(cleaned_code, language="python")