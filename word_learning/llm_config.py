from llama_cpp import Llama
from transformers import pipeline, AutoConfig
import os, random
import torch

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

def getllm_eval_wr():
    llm = Llama(
        model_path="/Users/yudi0/Desktop/SelfStudies/heavyfiles/Phi-3-mini-4k-instruct-q4.gguf",  # path to GGUF file
        n_ctx=2048,  # The max sequence length to use - note that longer sequence lengths require much more resources
        n_threads=8, # The number of CPU threads to use, tailor to your system and the resulting performance
        n_gpu_layers=0,
        temperature=0,
        top_k=3,
        top_p=0.95,
        
    )
    return llm

def llm_eval_wr(llm, content):
    try:
        with open("/Users/yudi0/Desktop/SelfStudies/vocab_learn/mysite/word_learning/document/writting_prompt.txt", 'r') as f:
            all_prompt = f.read()

        prompt = all_prompt + " " + content   
        
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

def llm_eval_wr(content):
    config = AutoConfig.from_pretrained("meta-llama/Llama-3.2-1B-Instruct")
    
    messages = [
        {"role": "user", "content":content}
    ]

    pipe = pipeline(
        "text-generation",
        model="meta-llama/Llama-3.2-1B-Instruct",
        torch_dtype=torch.float16,
        device="mps",
        model_kwargs={"low_cpu_mem_usage": True},
    )
    generation_config = {
        "num_return_sequences": 1,
        "max_new_tokens": 100j,
        "do_sample": False,
        "temperature": 0.1,
        "top_k": 1,
        "repetition_penalty": 1.2,
        "no_repeat_ngram_size": 3,
    }
    output = pipe(messages, **generation_config)
    output = output[0]['generated_txt'][1]['content']
    print(output)
    return output

"""