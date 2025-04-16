from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
import os
from dotenv import load_dotenv

load_dotenv()

class LLMAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        self.prompt = ChatPromptTemplate.from_template(
            "You are a helpful assistant. Please answer the following question: {question}"
        )
        
        self.chain = LLMChain(llm=self.llm, prompt=self.prompt)
    
    def get_response(self, question: str) -> str:
        """
        Get response from LLM for a given question
        
        Args:
            question (str): The question to ask
            
        Returns:
            str: The response from the LLM
        """
        try:
            response = self.chain.invoke({"question": question})
            return response["text"]
        except Exception as e:
            return f"Error getting response: {str(e)}"
