import os
import requests
import json
import autogen
import functools
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.chains.summarize import load_summarize_chain
from bs4 import BeautifulSoup
from langchain.chat_models import ChatOpenAI
from langsmith.run_helpers import traceable
from dotenv import load_dotenv
from autogen import config_list_from_json
from autogen.agentchat.contrib.gpt_assistant_agent import GPTAssistantAgent
from autogen import UserProxyAgent

# Load environment variables
load_dotenv()
BROWSERLESS_API_KEY = os.getenv("BROWSERLESS_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
assistant_id_1 = os.getenv("ASSISTANT_ID_1")
assistant_id_2 = os.getenv("ASSISTANT_ID_2")
assistant_id_3 = os.getenv("ASSISTANT_ID_3")

# Configuration for GPT assistants
config_list = config_list_from_json("OAI_CONFIG_LIST")

# Tracing with Langsmith
def traceable(run_type: str, name: str = None):
    def decorator_traceable(func):
        @functools.wraps(func)
        def wrapper_traceable(*args, **kwargs):
            print(f"Tracing {run_type} - {name if name else func.__name__}")
            # You can add more sophisticated tracing logic here
            return func(*args, **kwargs)
        return wrapper_traceable
    return decorator_traceable

# Function for google search
@traceable(run_type="tool", name="google_search")
def google_search(search_keyword):     
    url = "https://google.serper.dev/search"

    payload = json.dumps({
        "q": search_keyword
    })

    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    print("RESPONSE:", response.text)
    return response.text

# Function for summarizing
@traceable(run_type="tool", name="summary")
def summary(objective, content):
    llm = ChatOpenAI(temperature = 0, model = "gpt-3.5-turbo-16k-0613")

    text_splitter = RecursiveCharacterTextSplitter(separators=["\n\n", "\n"], chunk_size = 10000, chunk_overlap=500)
    docs = text_splitter.create_documents([content])
    
    map_prompt = """
    Write a summary of the following text for {objective}:
    "{text}"
    SUMMARY:
    """
    map_prompt_template = PromptTemplate(template=map_prompt, input_variables=["text", "objective"])
    
    summary_chain = load_summarize_chain(
        llm=llm, 
        chain_type='map_reduce',
        map_prompt = map_prompt_template,
        combine_prompt = map_prompt_template,
        verbose = False
    )

    output = summary_chain.run(input_documents=docs, objective=objective)

    return output

# Function for scraping
@traceable(run_type="tool", name="web_scraping")
def web_scraping(objective: str, url: str):
    print("Scraping website...")
    headers = {
        'Cache-Control': 'no-cache',
        'Content-Type': 'application/json',
    }

    data = {
        "url": url        
    }

    # Convert Python object to JSON string
    data_json = json.dumps(data)

    # Send the POST request
    response = requests.post(f"https://chrome.browserless.io/content?token={BROWSERLESS_API_KEY}", headers=headers, data=data_json)
    
    # Check the response status code
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        text = soup.get_text()
        print("CONTENTTTTTT:", text)
        if len(text) > 10000:
            output = summary(objective,text)
            return output
        else:
            return text
    else:
        print(f"HTTP request failed with status code {response.status_code}")    

# Create user proxy agent
user_proxy = UserProxyAgent(
    name="user_proxy",
    system_message="Help the user to answer their question concisely and accurately",
    is_termination_msg=lambda msg: "TERMINATE" in msg["content"],
    human_input_mode="ALWAYS",
    max_consecutive_auto_reply=10
)

@traceable(run_type="agent_creation", name="create_researcher_agent")
def create_researcher_agent(config_list, assistant_id):
    return GPTAssistantAgent(
        name="researcher",
        llm_config={
            "config_list": config_list,
            "assistant_id": assistant_id
        }
    )

# Usage
researcher = create_researcher_agent(config_list, assistant_id_1)

researcher.register_function(
    function_map={
        "web_scraping": web_scraping,
        "google_search": google_search,
    }
)

# Create research manager agent
research_manager = GPTAssistantAgent(
    name="research_manager",
    llm_config={
        "config_list": config_list,
        "assistant_id": assistant_id_2
    }
)

# Create director agent
director = GPTAssistantAgent(
    name="director",
    llm_config={
        "config_list": config_list,
        "assistant_id": assistant_id_3
    }
)

# Create group chat
groupchat = autogen.GroupChat(
    agents=[user_proxy, researcher, research_manager, director],
    messages=[],
    max_round=20
)

group_chat_manager = autogen.GroupChatManager(
    groupchat=groupchat, 
    llm_config={"config_list": config_list}
)

brand_task = input("Please enter the brand or company name: ")
user_task = input("Please enter your goal, brief, or problem statement: ")

user_proxy.initiate_chat(
    group_chat_manager, 
    message=user_task
)