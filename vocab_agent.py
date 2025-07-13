from models import VocabEntry, CEFRLevel
from typing_extensions import TypedDict
from typing import List
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
import os

from dotenv import load_dotenv
load_dotenv(override=True)
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "polynot")
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

# =========== LLM ===========
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    api_key=os.getenv('OPENAI_API_KEY')
)


# =========== State - which is passed thru all steps ===========
class State(TypedDict):
	topic: str
	target_language: str
	level: str
	vocab_list: list[str]
	vocab_entries: list[VocabEntry]


# =========== Nodes - functions ===========
def generate_vocabs(state: State):
	'''
		Just take the topic and level then append the vocab into vocab_list
	'''
	pass

def enrich_vocabs(state: State):
	'''
		Take vocab list in State, then iterate thru it with target_language and enrich it
		as VocabEntry format
	'''
	pass


def validate_enriched_vocabs(state: State):
	'''
		Validate all the result from above 
	'''
	pass


if __name__ == '__main__':
	messages = [
    (
        "system",
        "You are a helpful assistant that translates English to Vietnamese. Translate the user sentence.",
    ),
    ("human", "I love programming."),
]
	ai_msg = llm.invoke(messages)
	print(ai_msg)