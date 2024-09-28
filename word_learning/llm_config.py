from llama_cpp import Llama
import os, random

def get_llm():
    
    llm = Llama(
        model_path="/Users/yudi0/Desktop/SelfStudies/heavyfiles/Phi-3-mini-4k-instruct-q4.gguf",  # path to GGUF file
        n_ctx=1024,  # The max sequence length to use - note that longer sequence lengths require much more resources
        n_threads=8, # The number of CPU threads to use, tailor to your system and the resulting performance
        n_gpu_layers=35,
        tempreture=1.8,
        top_k=100,
        top_p=0.95
    )
    return llm


def example_sentence(input_word, llm):
    try:
        prompt = "Please write a sentence that contains the word " + input_word + "."
        output = llm(
            f"<|user|>\n{prompt}<|end|>\n<|assistant|>",
            max_tokens=32,  
            stop=["<|end|>"], 
            echo=True,  # Whether to echo the prompt
        )
        full_response = output['choices'][0]['text']
        assistant_tag = "<|assistant|>"
        start_index = full_response.find(assistant_tag)

        if start_index != -1:
            sentence  = full_response[start_index + len(assistant_tag):].strip()
        else:
            sentence = full_response.strip()
        return sentence
    
    except Exception as e:
        print(f"Error generating sentence: {e}")
        return "An error occurred while generating the sentence."

def get_llm_writting():
    
    llm = Llama(
        model_path="/Users/yudi0/Desktop/SelfStudies/heavyfiles/Phi-3-mini-4k-instruct-q4.gguf",  # path to GGUF file
        n_ctx=1024,  # The max sequence length to use - note that longer sequence lengths require much more resources
        n_threads=8, # The number of CPU threads to use, tailor to your system and the resulting performance
        n_gpu_layers=35,
        tempreture=1.8,
        top_k=100,
        top_p=0.95
    )
    return llm

def writingquiz_llm(llm):
    try:

        prompt = "Generate a single question in the same style as the following examples. Your response should contain only the new question, without any additional explanation or commentary: "
        with open("/Users/yudi0/Desktop/SelfStudies/vocab_learn/mysite/word_learning/document/writting_sample.txt", 'r') as f:
            all_samples = f.readlines()
        
        samples = random.sample(all_samples, 10)
        samples = ''.join(samples)
        prompt += samples
        print(prompt)

        output = llm(
            f"<|user|>\n{prompt}<|end|>\n<|assistant|>",
            max_tokens=256,  
            stop=["<|end|>"], 
            echo=True,  # Whether to echo the prompt
        )

        full_response = output['choices'][0]['text']
        assistant_tag = "<|assistant|>"
        start_index = full_response.find(assistant_tag)

        if start_index != -1:
            sentence  = full_response[start_index + len(assistant_tag):].strip()
        else:
            sentence = full_response.strip()
        return sentence
    
    except Exception as e:
        print(f"Error generating sentence: {e}")
        return "An error occurred while generating the sentence."








"""
import torch
from langchain_huggingface import HuggingFacePipeline
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from mysite import settings
from huggingface_hub import login




def get_llm(): # to prepare pipeline of llm model
  
    login(token=settings.HUGGINGFACE_TOKEN)
    
    model = AutoModelForCausalLM.from_pretrained(
        settings.HUGGINGFACE_MODEL_NAME,
        load_in_4bit=True,
        torch_dtype=torch.float16,
        device_map="auto",
        
    )

    tokenizer = AutoTokenizer.from_pretrained(settings.HUGGINGFACE_MODEL_NAME)

    generation_config = {
        "max_new_tokens" : 64,
        "do_sample" : False,
        "temperature" : None,
        "top_p" : None,
    }

    text_generation_pipeline = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device_map = "auto",
        **generation_config,
    )

    llm = HuggingFacePipeline(pipeline=text_generation_pipeline)
    return llm
    


def example_sentence(input_word, llm): # to create template input sentence
    llm_input = "Please write a sentence that contains the word " + input_word + "."
    llm_output_message = llm.invoke(llm_input)
    print(llm_output_message)


"""
    
